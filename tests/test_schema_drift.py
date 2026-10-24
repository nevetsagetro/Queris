from pathlib import Path

from queris.schema import ColumnSchema, DatabaseSchema, TableSchema
from queris.schema_drift import _write_invalidation_marker, compare_schemas


def _schema(columns: tuple[tuple[str, str], ...]) -> DatabaseSchema:
    return DatabaseSchema(
        tables=(
            TableSchema(
                schema_name="main",
                name="orders",
                columns=tuple(
                    ColumnSchema(
                        name=name,
                        data_type=data_type,
                        nullable=True,
                        ordinal_position=index,
                    )
                    for index, (name, data_type) in enumerate(columns, start=1)
                ),
            ),
        )
    )


def test_compare_schemas_reports_column_and_type_drift() -> None:
    drift = compare_schemas(
        _schema((("order_id", "INTEGER"), ("amount", "DOUBLE"))),
        _schema((("order_id", "BIGINT"), ("status", "VARCHAR"))),
    )

    assert drift.added_columns == ("orders.status",)
    assert drift.removed_columns == ("orders.amount",)
    assert drift.changed_types == ("orders.order_id",)
    assert drift.changed is True


def test_drift_marker_preserves_previous_intelligence_and_records_impact(tmp_path: Path) -> None:
    drift = compare_schemas(
        _schema((("order_id", "INTEGER"),)),
        _schema((("order_id", "BIGINT"),)),
    )

    _write_invalidation_marker(tmp_path, "orders", drift)

    marker = (tmp_path / "cache" / "orders.invalidation.json").read_text(encoding="utf-8")
    assert '"changed_types": [' in marker
