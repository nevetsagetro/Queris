from pathlib import Path

import pytest
from pydantic import ValidationError

from queris.database import read_only_connection
from queris.schema import ColumnSchema, DatabaseSchema, TableSchema, introspect_schema
from queris.schema_enrichment import (
    SchemaEnrichment,
    load_schema_enrichment,
    merge_reviewed_schema_enrichment,
    merge_schema_enrichment,
    validate_schema_enrichment,
)

RETAIL_ENRICHMENT_PATH = Path("metadata/retail.v1.yaml")


def _schema() -> DatabaseSchema:
    return DatabaseSchema(
        tables=(
            TableSchema(
                schema_name="main",
                name="orders",
                columns=(
                    ColumnSchema(
                        name="order_id",
                        data_type="INTEGER",
                        nullable=False,
                        ordinal_position=1,
                        sample_values=(1, 2),
                    ),
                    ColumnSchema(
                        name="order_date",
                        data_type="DATE",
                        nullable=False,
                        ordinal_position=2,
                        sample_values=("2026-01-01",),
                    ),
                ),
            ),
            TableSchema(
                schema_name="main",
                name="regions",
                columns=(
                    ColumnSchema(
                        name="name",
                        data_type="VARCHAR",
                        nullable=False,
                        ordinal_position=1,
                        sample_values=("North",),
                    ),
                ),
            ),
        )
    )


def test_load_schema_enrichment_reads_reviewed_versioned_metadata() -> None:
    enrichment = load_schema_enrichment(RETAIL_ENRICHMENT_PATH)

    assert enrichment.version == 1
    assert enrichment.reviewed is True
    assert [table.name for table in enrichment.tables] == [
        "categories",
        "order_items",
        "orders",
        "products",
        "regions",
    ]
    order_items = enrichment.tables[1]
    revenue = next(column for column in order_items.columns if column.name == "revenue")
    assert revenue.unit == "USD"
    assert "sales" in revenue.business_terms


def test_retail_enrichment_matches_live_schema(sample_database: Path) -> None:
    with read_only_connection(sample_database) as connection:
        schema = introspect_schema(connection, sample_limit=0)

    validation = validate_schema_enrichment(
        schema,
        load_schema_enrichment(RETAIL_ENRICHMENT_PATH),
    )

    assert validation.valid is True
    assert validation.issues == ()


@pytest.mark.parametrize(
    ("yaml_text", "error"),
    [
        ("version: 2\nreviewed: true\ntables: []\n", "version"),
        ("version: true\nreviewed: true\ntables: []\n", "version must be an integer"),
        ("version: 1\nreviewed: 'yes'\ntables: []\n", "valid boolean"),
        ("version: 1\nreviewed: true\ntables: []\n", "at least one table"),
        (
            """
            version: 1
            reviewed: true
            unknown: value
            tables:
              - schema_name: main
                name: orders
                description: Customer orders
            """,
            "Extra inputs are not permitted",
        ),
        (
            """
            version: 1
            reviewed: false
            tables:
              - schema_name: main
                name: orders
            """,
            "must define semantic metadata or columns",
        ),
        (
            """
            version: 1
            reviewed: true
            tables:
              - schema_name: main
                name: orders
                aliases: [Purchases, purchases]
            """,
            "labels must be unique",
        ),
    ],
)
def test_load_schema_enrichment_rejects_invalid_documents(
    tmp_path: Path,
    yaml_text: str,
    error: str,
) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml_text, encoding="utf-8")

    with pytest.raises(ValidationError, match=error):
        load_schema_enrichment(path)


@pytest.mark.parametrize(
    ("duplicate_yaml", "error"),
    [
        (
            """
            version: 1
            reviewed: true
            tables:
              - schema_name: main
                name: orders
                description: Orders
              - schema_name: MAIN
                name: Orders
                description: Duplicate orders
            """,
            "table references must be unique",
        ),
        (
            """
            version: 1
            reviewed: true
            tables:
              - schema_name: main
                name: orders
                columns:
                  - name: order_id
                    description: Order key
                  - name: ORDER_ID
                    aliases: [order key]
            """,
            "column references must be unique",
        ),
    ],
)
def test_load_schema_enrichment_rejects_duplicate_references(
    tmp_path: Path,
    duplicate_yaml: str,
    error: str,
) -> None:
    path = tmp_path / "duplicates.yaml"
    path.write_text(duplicate_yaml, encoding="utf-8")

    with pytest.raises(ValidationError, match=error):
        load_schema_enrichment(path)


def test_load_schema_enrichment_hides_yaml_parser_details(tmp_path: Path) -> None:
    path = tmp_path / "malformed.yaml"
    path.write_text("tables: [", encoding="utf-8")

    with pytest.raises(ValueError, match="could not be parsed"):
        load_schema_enrichment(path)


def test_merge_schema_enrichment_preserves_introspection_for_partial_metadata() -> None:
    schema = _schema()
    enrichment = SchemaEnrichment.model_validate(
        {
            "version": 1,
            "reviewed": True,
            "tables": [
                {
                    "schema_name": "main",
                    "name": "orders",
                    "description": "Customer orders.",
                    "aliases": ["sales orders"],
                    "columns": [
                        {
                            "name": "order_date",
                            "description": "Date the order was placed.",
                            "unit": "date",
                        }
                    ],
                }
            ],
        }
    )

    merged = merge_schema_enrichment(schema, enrichment)

    orders = merged.tables[0]
    assert orders.description == "Customer orders."
    assert orders.aliases == ("sales orders",)
    assert orders.columns[0] is schema.tables[0].columns[0]
    assert orders.columns[1].description == "Date the order was placed."
    assert orders.columns[1].unit == "date"
    assert orders.columns[1].data_type == "DATE"
    assert orders.columns[1].sample_values == ("2026-01-01",)
    assert merged.tables[1] is schema.tables[1]


def test_merge_reviewed_schema_enrichment_rejects_stale_metadata_before_activation() -> None:
    enrichment = SchemaEnrichment.model_validate(
        {
            "version": 1,
            "reviewed": True,
            "tables": [
                {
                    "schema_name": "main",
                    "name": "orders",
                    "columns": [{"name": "customer_id", "description": "Stale column."}],
                },
            ],
        }
    )

    with pytest.raises(ValueError, match=r"unknown_column main\.orders\.customer_id"):
        merge_reviewed_schema_enrichment(_schema(), enrichment)


def test_merge_reviewed_schema_enrichment_rejects_unreviewed_metadata() -> None:
    enrichment = SchemaEnrichment.model_validate(
        {
            "version": 1,
            "reviewed": False,
            "tables": [
                {
                    "schema_name": "main",
                    "name": "orders",
                    "description": "Unreviewed text.",
                },
            ],
        }
    )

    with pytest.raises(ValueError, match="reviewed"):
        merge_reviewed_schema_enrichment(_schema(), enrichment)


def test_validate_schema_enrichment_reports_structured_stale_references() -> None:
    enrichment = SchemaEnrichment.model_validate(
        {
            "version": 1,
            "reviewed": True,
            "tables": [
                {
                    "schema_name": "archive",
                    "name": "orders",
                    "description": "Stale schema.",
                },
                {
                    "schema_name": "main",
                    "name": "customers",
                    "description": "Stale table.",
                },
                {
                    "schema_name": "main",
                    "name": "orders",
                    "columns": [{"name": "customer_id", "description": "Stale column."}],
                },
            ],
        }
    )

    validation = validate_schema_enrichment(_schema(), enrichment)

    assert validation.valid is False
    assert [issue.model_dump(exclude_none=True) for issue in validation.issues] == [
        {"code": "unknown_schema", "schema_name": "archive"},
        {
            "code": "unknown_table",
            "schema_name": "main",
            "table_name": "customers",
        },
        {
            "code": "unknown_column",
            "schema_name": "main",
            "table_name": "orders",
            "column_name": "customer_id",
        },
    ]


@pytest.mark.parametrize(
    "document",
    [
        {
            "version": 1,
            "reviewed": False,
            "tables": [
                {
                    "schema_name": "main",
                    "name": "orders",
                    "description": "Unreviewed text.",
                }
            ],
        },
        {
            "version": 1,
            "reviewed": True,
            "tables": [
                {
                    "schema_name": "main",
                    "name": "missing_orders",
                    "description": "Stale table.",
                }
            ],
        },
        {
            "version": 1,
            "reviewed": True,
            "tables": [
                {
                    "schema_name": "main",
                    "name": "orders",
                    "columns": [{"name": "missing_date", "description": "Stale column."}],
                }
            ],
        },
    ],
)
def test_merge_schema_enrichment_does_not_activate_unreviewed_or_stale_metadata(
    document: dict[str, object],
) -> None:
    schema = _schema()

    merged = merge_schema_enrichment(schema, SchemaEnrichment.model_validate(document))

    assert merged is schema
