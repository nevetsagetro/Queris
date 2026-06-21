from pathlib import Path

import duckdb
import pytest

import queris.agent_loop as agent_loop
from queris.agent_loop import run_agent_loop
from queris.generation import SQLCorrectionContext
from queris.pipeline import FullSchemaSelector
from queris.schema import DatabaseSchema


class FakeGenerator:
    def __init__(self, *sql_attempts: str) -> None:
        self.sql_attempts = sql_attempts
        self.calls: list[tuple[DatabaseSchema, str, SQLCorrectionContext | None]] = []

    def generate_sql(
        self,
        schema: DatabaseSchema,
        question: str,
        correction: SQLCorrectionContext | None = None,
    ) -> str:
        self.calls.append((schema, question, correction))
        index = min(len(self.calls) - 1, len(self.sql_attempts) - 1)
        return self.sql_attempts[index]


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
    assert result.sql == generator.sql_attempts[0]
    assert result.columns == ("order_count",)
    assert result.rows == ((4,),)
    assert result.failure_stage is None
    assert result.error is None
    assert generator.calls[0][1] == result.question
    assert generator.calls[0][2] is None


def test_agent_loop_stops_unsafe_sql_before_execution(
    sample_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_execution(connection: object, sql: str) -> object:
        pytest.fail(f"unsafe SQL reached execution: {sql}")

    monkeypatch.setattr(agent_loop, "execute_read_only", forbidden_execution)
    generator = FakeGenerator("DROP TABLE orders")

    result = run_agent_loop(
        sample_database,
        "Delete all orders",
        generator,
        FullSchemaSelector(),
    )

    assert result.status == "failure"
    assert result.failure_stage == "validation"
    assert result.error is not None
    assert result.rows == ()
    assert len(result.sql) > 0
    assert len(generator.calls) == 2
    assert generator.calls[1][2] is not None


def test_agent_loop_returns_execution_failure_for_invalid_query(
    sample_database: Path,
) -> None:
    generator = FakeGenerator("SELECT COUNT(*) FROM missing_table")

    result = run_agent_loop(
        sample_database,
        "Count missing records",
        generator,
        FullSchemaSelector(),
    )

    assert result.status == "failure"
    assert result.failure_stage == "execution"
    assert result.error is not None
    assert "missing_table" in result.error
    assert result.rows == ()
    assert len(generator.calls) == 2
    assert generator.calls[1][2] is not None


def test_agent_loop_corrects_validation_failure_before_execution(
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
    generator = FakeGenerator("DROP TABLE orders", "SELECT COUNT(*) FROM orders")

    result = run_agent_loop(
        sample_database,
        "How many orders are there?",
        generator,
        FullSchemaSelector(),
    )

    assert result.status == "success"
    assert result.rows == ((4,),)
    assert executed_sql == ["SELECT COUNT(*) FROM orders"]
    correction = generator.calls[1][2]
    assert correction is not None
    assert correction.previous_sql == "DROP TABLE orders"
    assert correction.failure_stage == "validation"


def test_agent_loop_corrects_execution_failure(sample_database: Path) -> None:
    generator = FakeGenerator(
        "SELECT COUNT(*) FROM missing_table",
        "SELECT COUNT(*) FROM orders",
    )

    result = run_agent_loop(
        sample_database,
        "How many orders are there?",
        generator,
        FullSchemaSelector(),
    )

    assert result.status == "success"
    assert result.sql == "SELECT COUNT(*) FROM orders"
    assert result.rows == ((4,),)
    correction = generator.calls[1][2]
    assert correction is not None
    assert correction.previous_sql == "SELECT COUNT(*) FROM missing_table"
    assert correction.failure_stage == "execution"
    assert "missing_table" in correction.error


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
    assert executed_sql == [generator.sql_attempts[0]]


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
