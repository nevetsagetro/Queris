from queris.schema import ColumnSchema, DatabaseSchema, TableSchema
from queris.schema_enrichment import JoinHint, SchemaEnrichment, validate_schema_enrichment


def test_join_hints_are_validated_against_live_schema() -> None:
    schema = DatabaseSchema(
        tables=(
            TableSchema(
                schema_name="main",
                name="orders",
                columns=(
                    ColumnSchema(
                        name="customer_id",
                        data_type="INTEGER",
                        nullable=False,
                        ordinal_position=1,
                    ),
                ),
            ),
        )
    )
    enrichment = SchemaEnrichment(
        version=1,
        reviewed=False,
        tables=(
            {"schema_name": "main", "name": "orders", "description": "Orders."},
        ),
        join_hints=(
            JoinHint(
                left_schema="main",
                left_table="orders",
                left_column="missing_id",
                right_schema="main",
                right_table="customers",
                right_column="customer_id",
                rationale="Potential customer relationship.",
            ),
        ),
    )

    validation = validate_schema_enrichment(schema, enrichment)

    assert not validation.valid
    assert len(validation.issues) == 2
