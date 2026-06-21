import json
import sys
from pathlib import Path

import duckdb
import pytest

from queris.database import read_only_connection
from queris.schema import MAX_SAMPLE_VALUES, introspect_schema, main


def test_introspect_schema_returns_ordered_tables(sample_database: Path) -> None:
    with read_only_connection(sample_database) as connection:
        schema = introspect_schema(connection)

    assert [table.name for table in schema.tables] == [
        "categories",
        "order_items",
        "orders",
        "products",
        "regions",
    ]
    assert all(table.schema_name == "main" for table in schema.tables)


def test_introspect_schema_describes_columns(sample_database: Path) -> None:
    with read_only_connection(sample_database) as connection:
        schema = introspect_schema(connection)

    orders = next(table for table in schema.tables if table.name == "orders")
    assert [(column.name, column.data_type, column.nullable) for column in orders.columns] == [
        ("order_id", "INTEGER", False),
        ("order_date", "DATE", False),
        ("region_id", "INTEGER", False),
    ]
    assert orders.columns[0].ordinal_position == 1


def test_introspect_schema_limits_sample_values(sample_database: Path) -> None:
    with read_only_connection(sample_database) as connection:
        schema = introspect_schema(connection, sample_limit=2)

    regions = next(table for table in schema.tables if table.name == "regions")
    names = next(column for column in regions.columns if column.name == "name")
    assert len(names.sample_values) == 2
    assert set(names.sample_values).issubset({"North", "South", "West"})


def test_introspect_schema_can_omit_sample_values(sample_database: Path) -> None:
    with read_only_connection(sample_database) as connection:
        schema = introspect_schema(connection, sample_limit=0)

    assert all(not column.sample_values for table in schema.tables for column in table.columns)


@pytest.mark.parametrize("sample_limit", [-1, MAX_SAMPLE_VALUES + 1])
def test_introspect_schema_rejects_unsafe_sample_limits(
    sample_database: Path,
    sample_limit: int,
) -> None:
    with (
        read_only_connection(sample_database) as connection,
        pytest.raises(ValueError, match="sample_limit"),
    ):
        introspect_schema(connection, sample_limit=sample_limit)


def test_introspect_schema_quotes_identifiers(tmp_path: Path) -> None:
    database_path = tmp_path / "quoted.duckdb"
    connection = duckdb.connect(str(database_path))
    connection.execute('CREATE TABLE "odd""table" ("odd""column" VARCHAR)')
    connection.execute('INSERT INTO "odd""table" VALUES (\'safe\')')
    connection.close()

    with read_only_connection(database_path) as connection:
        schema = introspect_schema(connection)

    assert schema.tables[0].name == 'odd"table'
    assert schema.tables[0].columns[0].name == 'odd"column'
    assert schema.tables[0].columns[0].sample_values == ("safe",)


def test_schema_cli_prints_json(
    sample_database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["queris-schema", str(sample_database), "--samples", "0"])

    main()

    output = json.loads(capsys.readouterr().out)
    assert output["tables"][0]["name"] == "categories"
