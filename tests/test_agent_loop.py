from pathlib import Path

import duckdb
import pytest

import queris.agent_loop as agent_loop
from queris.agent_loop import (
    DEFAULT_MAX_RETRIES,
    MAX_RETRIES,
    QuestionResolution,
    run_agent_loop,
)
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


class FakeResolver:
    def __init__(self, resolution: QuestionResolution) -> None:
        self.resolution = resolution
        self.calls: list[tuple[DatabaseSchema, str]] = []

    def resolve(self, schema: DatabaseSchema, question: str) -> QuestionResolution:
        self.calls.append((schema, question))
        return self.resolution


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
    assert len(result.sources) == 1
    assert result.sources[0].table_name == "orders"
    assert result.sources[0].columns == ("*",)
    assert result.failure_stage is None
    assert result.error is None
    assert result.retry_count == 0
    assert result.retries_exhausted is False
    assert result.explanation is None
    assert result.clarification is None
    assert result.assumption is None
    assert generator.calls[0][1] == result.question
    assert generator.calls[0][2] is None


def test_agent_loop_records_total_latency(
    sample_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readings = iter((10.0, 10.125))
    monkeypatch.setattr(agent_loop, "perf_counter", lambda: next(readings))

    result = run_agent_loop(
        sample_database,
        "How many orders are there?",
        FakeGenerator("SELECT COUNT(*) FROM orders"),
        FullSchemaSelector(),
        sample_limit=0,
    )

    assert result.latency_ms == pytest.approx(125)


def test_agent_loop_requests_clarification_before_generation(
    sample_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_execution(connection: object, sql: str) -> object:
        pytest.fail(f"ambiguous question reached execution: {sql}")

    monkeypatch.setattr(agent_loop, "execute_read_only", forbidden_execution)
    generator = FakeGenerator("SELECT COUNT(*) FROM orders")
    resolver = FakeResolver(
        QuestionResolution(
            kind="clarification",
            message="Do you mean revenue, units, or order count?",
        )
    )

    result = run_agent_loop(
        sample_database,
        "Show sales by region",
        generator,
        FullSchemaSelector(),
        question_resolver=resolver,
    )

    assert result.status == "clarification"
    assert result.sql is None
    assert result.clarification == "Do you mean revenue, units, or order count?"
    assert result.assumption is None
    assert generator.calls == []
    assert resolver.calls[0][1] == "Show sales by region"


def test_agent_loop_returns_no_answer_before_generation(
    sample_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_execution(connection: object, sql: str) -> object:
        pytest.fail(f"unanswerable question reached execution: {sql}")

    monkeypatch.setattr(agent_loop, "execute_read_only", forbidden_execution)
    generator = FakeGenerator("SELECT social_security_number FROM customers")
    resolver = FakeResolver(
        QuestionResolution(
            kind="no_answer",
            message="The live schema does not contain social security numbers.",
        )
    )

    result = run_agent_loop(
        sample_database,
        "Show every customer's social security number.",
        generator,
        FullSchemaSelector(),
        question_resolver=resolver,
    )

    assert result.status == "no_answer"
    assert result.sql is None
    assert result.no_answer == "The live schema does not contain social security numbers."
    assert result.clarification is None
    assert result.assumption is None
    assert generator.calls == []
    assert resolver.calls[0][1] == "Show every customer's social security number."


def test_agent_loop_records_explicit_assumption(sample_database: Path) -> None:
    generator = FakeGenerator("SELECT COUNT(*) FROM orders WHERE order_date >= DATE '2026-04-01'")
    resolver = FakeResolver(
        QuestionResolution(
            kind="assumption",
            message="Assuming recent means orders on or after 2026-04-01.",
        )
    )

    result = run_agent_loop(
        sample_database,
        "Show recent orders",
        generator,
        FullSchemaSelector(),
        question_resolver=resolver,
    )

    assert result.status == "success"
    assert result.assumption == "Assuming recent means orders on or after 2026-04-01."
    assert result.clarification is None
    assert result.rows == ((2,),)


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
    assert len(generator.calls) == DEFAULT_MAX_RETRIES + 1
    assert all(call[2] is not None for call in generator.calls[1:])
    assert result.retries_exhausted is True
    assert result.retry_count == DEFAULT_MAX_RETRIES
    assert result.explanation == "Could not produce executable read-only SQL after 4 attempts."


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
    assert len(generator.calls) == DEFAULT_MAX_RETRIES + 1
    assert all(call[2] is not None for call in generator.calls[1:])
    assert result.retries_exhausted is True
    assert result.retry_count == DEFAULT_MAX_RETRIES
    assert result.explanation == "Could not produce executable read-only SQL after 4 attempts."


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
    assert result.retry_count == 1
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
    assert result.retry_count == 1
    correction = generator.calls[1][2]
    assert correction is not None
    assert correction.previous_sql == "SELECT COUNT(*) FROM missing_table"
    assert correction.failure_stage == "execution"
    assert "missing_table" in correction.error


def test_agent_loop_uses_configured_retry_cap(sample_database: Path) -> None:
    generator = FakeGenerator(
        "SELECT COUNT(*) FROM missing_one",
        "SELECT COUNT(*) FROM missing_two",
        "SELECT COUNT(*) FROM orders",
    )

    result = run_agent_loop(
        sample_database,
        "How many orders are there?",
        generator,
        FullSchemaSelector(),
        max_retries=2,
    )

    assert result.status == "success"
    assert result.rows == ((4,),)
    assert len(generator.calls) == 3
    assert result.retry_count == 2


def test_agent_loop_can_disable_retries(sample_database: Path) -> None:
    generator = FakeGenerator("SELECT COUNT(*) FROM missing_table")

    result = run_agent_loop(
        sample_database,
        "How many orders are there?",
        generator,
        FullSchemaSelector(),
        max_retries=0,
    )

    assert result.status == "failure"
    assert result.retries_exhausted is True
    assert result.retry_count == 0
    assert result.explanation == "Could not produce executable read-only SQL after 1 attempt."
    assert len(generator.calls) == 1


def test_agent_loop_supports_maximum_retry_cap(sample_database: Path) -> None:
    generator = FakeGenerator("DROP TABLE orders")

    result = run_agent_loop(
        sample_database,
        "Delete all orders",
        generator,
        FullSchemaSelector(),
        max_retries=MAX_RETRIES,
    )

    assert result.status == "failure"
    assert result.retries_exhausted is True
    assert result.retry_count == MAX_RETRIES
    assert len(generator.calls) == MAX_RETRIES + 1


@pytest.mark.parametrize("max_retries", [-1, MAX_RETRIES + 1, 1.5, True])
def test_agent_loop_rejects_invalid_retry_cap_before_generation(
    sample_database: Path,
    max_retries: object,
) -> None:
    generator = FakeGenerator("SELECT 1")

    with pytest.raises(ValueError, match="max_retries"):
        run_agent_loop(
            sample_database,
            "Return one",
            generator,
            FullSchemaSelector(),
            max_retries=max_retries,  # type: ignore[arg-type]
        )

    assert generator.calls == []


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
