import pytest

from queris.adapters import PostgresAdapter
from queris.sql_validation import SQLValidationError


class FakeCursor:
    description = (("value",),)

    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, sql: str) -> None:
        self.executed.append(sql)

    def fetchall(self) -> list[tuple[int]]:
        return [(1,)]

    def close(self) -> None:
        pass

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class FakeConnection:
    def __init__(self) -> None:
        self.cursors: list[FakeCursor] = []

    def cursor(self) -> FakeCursor:
        cursor = FakeCursor()
        self.cursors.append(cursor)
        return cursor

    def close(self) -> None:
        pass


def test_postgres_adapter_prepares_read_only_session_and_executes_select() -> None:
    connection = FakeConnection()
    adapter = PostgresAdapter("postgresql://redacted", connect_factory=lambda _dsn: connection)

    result = adapter.execute("SELECT 1")

    assert result.columns == ("value",)
    assert result.rows == ((1,),)
    session_sql = connection.cursors[0].executed
    query_sql = connection.cursors[1].executed
    assert "read_only" in session_sql[0]
    assert "statement_timeout" in session_sql[1]
    assert query_sql == ["SELECT 1"]


def test_postgres_adapter_rejects_mutation_before_connecting() -> None:
    calls: list[str] = []
    adapter = PostgresAdapter(
        "postgresql://redacted", connect_factory=lambda dsn: calls.append(dsn)
    )

    with pytest.raises(SQLValidationError):
        adapter.execute("DELETE FROM orders")

    assert calls == []
