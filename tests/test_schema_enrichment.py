from pathlib import Path

import pytest
from pydantic import ValidationError

from queris.schema_enrichment import load_schema_enrichment

RETAIL_ENRICHMENT_PATH = Path("metadata/retail.v1.yaml")


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
