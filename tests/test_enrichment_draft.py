import sys
from pathlib import Path

import yaml

from queris.enrichment_draft import draft_schema_enrichment, main
from queris.schema import ColumnSchema, DatabaseSchema, TableSchema
from queris.schema_enrichment import SchemaEnrichment, merge_schema_enrichment


def test_draft_schema_enrichment_uses_identifiers_and_types() -> None:
    schema = DatabaseSchema(
        tables=(
            TableSchema(
                schema_name="analytics",
                name="orders",
                columns=(
                    ColumnSchema(
                        name="order_id",
                        data_type="BIGINT",
                        nullable=False,
                        ordinal_position=1,
                        sample_values=(101, 102),
                    ),
                ),
            ),
        )
    )

    draft = draft_schema_enrichment(schema)

    assert draft.version == 1
    assert draft.reviewed is False
    assert draft.tables[0].description == "Table analytics.orders."
    assert draft.tables[0].columns[0].description == ("BIGINT column analytics.orders.order_id.")
    assert merge_schema_enrichment(schema, draft) is schema


def test_enrichment_draft_cli_emits_valid_inactive_yaml_without_samples(
    sample_database: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(sys, "argv", ["queris-enrichment-draft", str(sample_database)])

    main()

    output = capsys.readouterr().out
    document = yaml.safe_load(output)
    draft = SchemaEnrichment.model_validate(document)
    assert draft.reviewed is False
    assert [table.name for table in draft.tables] == [
        "categories",
        "order_items",
        "orders",
        "products",
        "regions",
    ]
    assert "North" not in output
    assert "Notebook" not in output
