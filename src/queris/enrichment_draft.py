"""Draft inactive schema-enrichment metadata from DuckDB introspection."""

import argparse
from pathlib import Path

import yaml

from queris.database import read_only_connection
from queris.schema import DatabaseSchema, introspect_schema
from queris.schema_enrichment import ColumnEnrichment, SchemaEnrichment, TableEnrichment


def draft_schema_enrichment(schema: DatabaseSchema) -> SchemaEnrichment:
    """Create a version 1 enrichment scaffold that requires human review."""
    return SchemaEnrichment(
        version=1,
        reviewed=False,
        tables=tuple(
            TableEnrichment(
                schema_name=table.schema_name,
                name=table.name,
                description=f"Table {table.schema_name}.{table.name}.",
                columns=tuple(
                    ColumnEnrichment(
                        name=column.name,
                        description=(
                            f"{column.data_type} column "
                            f"{table.schema_name}.{table.name}.{column.name}."
                        ),
                    )
                    for column in table.columns
                ),
            )
            for table in schema.tables
        ),
    )


def dump_schema_enrichment(enrichment: SchemaEnrichment) -> str:
    """Serialize enrichment as stable, safe YAML for review."""
    document = enrichment.model_dump(
        mode="json",
        exclude_none=True,
        exclude_defaults=True,
    )
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Draft inactive schema-enrichment YAML for human review"
    )
    parser.add_argument("database", type=Path, help="Existing .duckdb path")
    args = parser.parse_args()

    with read_only_connection(args.database) as connection:
        schema = introspect_schema(connection, sample_limit=0)
    print(dump_schema_enrichment(draft_schema_enrichment(schema)), end="")


if __name__ == "__main__":
    main()
