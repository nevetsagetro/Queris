from pathlib import Path
from typing import Self

import duckdb
import pytest

from queris.database import execute_read_only, read_only_connection
from queris.sample_data import create_sample_database
from queris.sql_validation import SQLValidationError


def test_create_sample_database_loads_expected_rows(sample_database: Path) -> None:
    with read_only_connection(sample_database) as connection:
        assert connection.execute("SELECT count(*) FROM orders").fetchone() == (4,)
        assert connection.execute("SELECT count(*) FROM order_items").fetchone() == (5,)


def test_create_sample_database_refuses_to_replace_existing_file(
    sample_database: Path,
) -> None:
    with pytest.raises(FileExistsError, match="Refusing to replace"):
        create_sample_database(sample_database)


def test_read_only_connection_rejects_writes(sample_database: Path) -> None:
    with (
        read_only_connection(sample_database) as connection,
        pytest.raises(duckdb.Error, match="read-only mode"),
    ):
        connection.execute("CREATE TABLE forbidden (value INTEGER)")


def test_read_only_connection_requires_existing_file(tmp_path: Path) -> None:
    with (
        pytest.raises(FileNotFoundError, match="does not exist"),
        read_only_connection(tmp_path / "missing.duckdb"),
    ):
        pass


class RecordingConnection:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> Self:
        self.executed_sql.append(sql)
        return self


def test_execute_read_only_validates_before_execution() -> None:
    connection = RecordingConnection()

    with pytest.raises(SQLValidationError, match="Only read-only"):
        execute_read_only(connection, "DROP TABLE orders")

    assert connection.executed_sql == []


def test_execute_read_only_sends_validated_query_to_connection() -> None:
    connection = RecordingConnection()

    result = execute_read_only(connection, "SELECT 1")

    assert result is connection
    assert connection.executed_sql == ["SELECT 1"]
