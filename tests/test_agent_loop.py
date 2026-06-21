from pathlib import Path

import duckdb
import pytest

import queris.agent_loop as agent_loop
from queris.agent_loop import run_agent_loop
from queris.pipeline import FullSchemaSelector
from queris.schema import DatabaseSchema


class FakeGenerator:
    def __init__(self, sql: str) -> None:
        self.sql = sql
        self.calls: list[tuple[DatabaseSchema, str]] = []

    def generate_sql(self, schema: DatabaseSchema, question: str) -> str:
        self.calls.append((schema, question))
        return self.sql


def test_agent_loop_returns_typed_success(sample_database: Path) -> None:
    generator = FakeGenerator("SELECT COUNT(*) AS order_count FROM orders")

    result = run_agent_loop(
        sample_database,
        "  How many orders are there?  ",
        generator,
        FullSchemaSelector(),
        sample_limit=0,
    )

    assert result.status == "success"
    assert result.question == "How many orders are there?"
    assert result.sql == generator.sql
    assert result.columns == ("order_count",)
    assert result.rows == ((4,),)
    assert result.failure_stage is None
    assert result.error is None
    assert generator.calls[0][1] == result.question


def test_agent_loop_stops_unsafe_sql_before_execution(
    sample_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_execution(connection: object, sql: str) -> object:
        pytest.fail(f"unsafe SQL reached execution: {sql}")

    monkeypatch.setattr(agent_loop, "execute_read_only", forbidden_execution)

    result = run_agent_loop(
        sample_database,
        "Delete all orders",
        FakeGenerator("DROP TABLE orders"),
        FullSchemaSelector(),
    )

    assert result.status == "failure"
    assert result.failure_stage == "validation"
    assert result.error is not None
    assert result.rows == ()


def test_agent_loop_returns_execution_failure_for_invalid_query(
    sample_database: Path,
) -> None:
    result = run_agent_loop(
        sample_database,
        "Count missing records",
        FakeGenerator("SELECT COUNT(*) FROM missing_table"),
        FullSchemaSelector(),
    )

    assert result.status == "failure"
    assert result.failure_stage == "execution"
    assert result.error is not None
    assert "missing_table" in result.error
    assert result.rows == ()


def test_agent_loop_executes_through_validating_adapter(
    sample_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed_sql: list[str] = []
    original_execute = agent_loop.execute_read_only

    def recording_execute(
        connection: duckdb.DuckDBPyConnection,
        sql: str,
    ) -> duckdb.DuckDBPyConnection:
        executed_sql.append(sql)
        return original_execute(connection, sql)

    monkeypatch.setattr(agent_loop, "execute_read_only", recording_execute)
    generator = FakeGenerator("SELECT 1")

    result = run_agent_loop(
        sample_database,
        "Return one",
        generator,
        FullSchemaSelector(),
    )

    assert result.status == "success"
    assert executed_sql == [generator.sql]


@pytest.mark.parametrize("question", ["", "   "])
def test_agent_loop_rejects_empty_question(sample_database: Path, question: str) -> None:
    generator = FakeGenerator("SELECT 1")

    with pytest.raises(ValueError, match="question"):
        run_agent_loop(sample_database, question, generator, FullSchemaSelector())

    assert generator.calls == []


def test_agent_loop_rejects_non_string_question(sample_database: Path) -> None:
    generator = FakeGenerator("SELECT 1")

    with pytest.raises(TypeError, match="question"):
        run_agent_loop(  # type: ignore[arg-type]
            sample_database,
            None,
            generator,
            FullSchemaSelector(),
        )

    assert generator.calls == []
