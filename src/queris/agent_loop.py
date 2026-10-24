"""Typed LangGraph foundation for bounded text-to-SQL orchestration."""

from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, NotRequired, Protocol, Self, TypedDict

import duckdb
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, Field, model_validator

from queris.database import execute_read_only, read_only_connection
from queris.generation import SQLCorrectionContext
from queris.pipeline import SchemaSelector
from queris.query_sources import QuerySource, extract_query_sources
from queris.schema import DatabaseSchema, introspect_schema
from queris.sql_validation import SQLValidationError, parse_read_only

FailureStage = Literal["validation", "execution"]
DEFAULT_MAX_RETRIES = 3
MAX_RETRIES = 10
_GRAPH_STEPS_PER_ATTEMPT = 4


class CorrectingSQLGenerator(Protocol):
    """Generate initial SQL and corrections from failed-attempt context."""

    def generate_sql(
        self,
        schema: DatabaseSchema,
        question: str,
        correction: SQLCorrectionContext | None = None,
    ) -> str: ...


class QuestionResolution(BaseModel):
    """Structured pre-generation decision for a question that should not go to SQL."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["clarification", "assumption", "no_answer"]
    message: str = Field(min_length=1)


class QuestionResolver(Protocol):
    """Resolve pre-generation question handling or return no intervention."""

    def resolve(self, schema: DatabaseSchema, question: str) -> QuestionResolution | None: ...


class AgentQueryResult(BaseModel):
    """Terminal query, failure, clarification, or no-answer from orchestration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["success", "failure", "clarification", "no_answer"]
    question: str
    sql: str | None
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    sources: tuple[QuerySource, ...] = ()
    failure_stage: FailureStage | None = None
    error: str | None = None
    retry_count: int = Field(ge=0)
    latency_ms: float = Field(default=0, ge=0)
    retries_exhausted: bool = False
    explanation: str | None = None
    clarification: str | None = None
    assumption: str | None = None
    no_answer: str | None = None

    @property
    def blocked(self) -> bool:
        """Return whether validation blocked the terminal SQL before execution."""
        return self.status == "failure" and self.failure_stage == "validation"

    @model_validator(mode="after")
    def require_consistent_terminal_state(self) -> Self:
        if self.status == "success":
            if not self.sql or any(
                (
                    self.failure_stage is not None,
                    self.error is not None,
                    self.retries_exhausted,
                    self.explanation is not None,
                    self.clarification is not None,
                    self.no_answer is not None,
                )
            ):
                raise ValueError("successful result must contain SQL without failure details")
        elif self.status == "failure":
            if (
                not self.sql
                or self.failure_stage is None
                or not self.error
                or not self.retries_exhausted
                or not self.explanation
                or self.clarification is not None
                or self.no_answer is not None
            ):
                raise ValueError("failed result must contain SQL and failure details")
        elif self.status == "clarification" and (
            self.sql is not None
            or self.failure_stage is not None
            or self.error is not None
            or self.retries_exhausted
            or self.explanation is not None
            or not self.clarification
            or self.assumption is not None
            or self.no_answer is not None
            or self.retry_count != 0
            or self.columns
            or self.rows
            or self.sources
        ):
            raise ValueError("clarification result must terminate before SQL generation")
        elif self.status == "no_answer" and (
            self.sql is not None
            or self.failure_stage is not None
            or self.error is not None
            or self.retries_exhausted
            or self.explanation is not None
            or self.clarification is not None
            or self.assumption is not None
            or not self.no_answer
            or self.retry_count != 0
            or self.columns
            or self.rows
            or self.sources
        ):
            raise ValueError("no-answer result must terminate before SQL generation")
        return self


class _AgentState(TypedDict):
    question: str
    schema: DatabaseSchema
    sql: NotRequired[str]
    status: NotRequired[Literal["success", "failure"] | None]
    columns: NotRequired[tuple[str, ...]]
    rows: NotRequired[tuple[tuple[Any, ...], ...]]
    failure_stage: NotRequired[FailureStage | None]
    error: NotRequired[str | None]
    correction: NotRequired[SQLCorrectionContext | None]
    retry_count: int
    max_retries: int


def run_agent_loop(
    database_path: str | Path,
    question: str,
    generator: CorrectingSQLGenerator,
    schema_selector: SchemaSelector,
    *,
    sample_limit: int = 3,
    max_retries: int = DEFAULT_MAX_RETRIES,
    question_resolver: QuestionResolver | None = None,
    progress_callback: Callable[[str], None] | None = None,
    schema_override: DatabaseSchema | None = None,
    adapter: Any | None = None,
) -> AgentQueryResult:
    """Run generate, validate, and execute with a bounded correction loop.

    ``adapter`` is an optional read-only database boundary for live engines.
    The default remains the local DuckDB snapshot path.
    """
    normalized_question = _normalize_question(question)
    _validate_max_retries(max_retries)
    started_at = perf_counter()
    _report_progress(progress_callback, "Sending question to Queris...")

    if adapter is not None:
        if schema_override is None:
            _report_progress(progress_callback, "Analyzing live database schema...")
            schema = adapter.introspect(sample_limit=sample_limit)
        else:
            _report_progress(progress_callback, "Using cached schema catalog...")
            schema = schema_override
        state, assumption = _run_graph(
            schema,
            normalized_question,
            generator,
            schema_selector,
            lambda sql: _adapter_result(adapter.execute(sql)),
            question_resolver,
            max_retries,
            progress_callback,
            execution_label="live read-only adapter",
        )
    else:
        with read_only_connection(database_path) as connection:
            if schema_override is None:
                _report_progress(progress_callback, "Analyzing database schema...")
                schema = introspect_schema(connection, sample_limit=sample_limit)
            else:
                _report_progress(progress_callback, "Using cached schema catalog...")
                schema = schema_override
            state, assumption = _run_graph(
                schema,
                normalized_question,
                generator,
                schema_selector,
                lambda sql: _duckdb_result(connection, sql),
                question_resolver,
                max_retries,
                progress_callback,
                execution_label="DuckDB (read-only)",
            )

    if state["status"] == "clarification":
        return AgentQueryResult(
            status="clarification",
            question=normalized_question,
            sql=None,
            retry_count=0,
            latency_ms=_elapsed_ms(started_at),
            clarification=state.get("clarification"),
        )
    if state["status"] == "no_answer":
        return AgentQueryResult(
            status="no_answer",
            question=normalized_question,
            sql=None,
            retry_count=0,
            latency_ms=_elapsed_ms(started_at),
            no_answer=state.get("no_answer"),
        )
    failed = state["status"] == "failure"
    sources = extract_query_sources(state["sql"], schema) if not failed else ()
    return AgentQueryResult(
        status=state["status"],
        question=normalized_question,
        sql=state["sql"],
        columns=state.get("columns", ()),
        rows=state.get("rows", ()),
        sources=sources,
        failure_stage=state.get("failure_stage"),
        error=state.get("error"),
        retry_count=state["retry_count"],
        latency_ms=_elapsed_ms(started_at),
        retries_exhausted=failed,
        explanation=_build_exhaustion_explanation(state["retry_count"]) if failed else None,
        assumption=assumption,
    )


def _build_graph(
    execute_query: Callable[[str], tuple[tuple[str, ...], tuple[tuple[Any, ...], ...]]],
    generator: CorrectingSQLGenerator,
    schema_selector: SchemaSelector,
    progress_callback: Callable[[str], None] | None = None,
    execution_label: str = "DuckDB (read-only)",
) -> CompiledStateGraph[_AgentState, None, _AgentState, _AgentState]:
    def generate(state: _AgentState) -> dict[str, object]:
        _report_progress(progress_callback, "Selecting relevant tables and generating SQL...")
        selected_schema = schema_selector.select_schema(state["schema"], state["question"])
        return {
            "sql": generator.generate_sql(
                selected_schema,
                state["question"],
                state.get("correction"),
            ),
            "status": None,
            "failure_stage": None,
            "error": None,
        }

    def validate(state: _AgentState) -> dict[str, str]:
        _report_progress(progress_callback, "Validating SQL against the read-only safety policy...")
        try:
            parse_read_only(state["sql"])
        except SQLValidationError as error:
            return {
                "status": "failure",
                "failure_stage": "validation",
                "error": str(error),
            }
        return {}

    def execute(state: _AgentState) -> dict[str, object]:
        _report_progress(progress_callback, f"Executing validated SQL on {execution_label}...")
        try:
            columns, rows = execute_query(state["sql"])
        except SQLValidationError as error:
            return {
                "status": "failure",
                "failure_stage": "validation",
                "error": str(error),
            }
        except Exception as error:
            return {
                "status": "failure",
                "failure_stage": "execution",
                "error": str(error),
            }
        return {
            "status": "success",
            "columns": columns,
            "rows": rows,
        }

    def prepare_correction(state: _AgentState) -> dict[str, object]:
        failure_stage = state.get("failure_stage")
        error = state.get("error")
        if failure_stage is None or error is None:
            raise RuntimeError("failed graph state is missing correction diagnostics")
        _report_progress(
            progress_callback,
            "Retrying SQL generation with the database feedback...",
        )
        return {
            "correction": SQLCorrectionContext(
                previous_sql=state["sql"],
                failure_stage=failure_stage,
                error=error,
            ),
            "retry_count": state["retry_count"] + 1,
        }

    def route_failed_state(state: _AgentState) -> str:
        if state.get("status") != "failure":
            return "success"
        return "failure" if state["retry_count"] >= state["max_retries"] else "correct"

    graph = StateGraph(_AgentState)
    graph.add_node("generate", generate)
    graph.add_node("validate", validate)
    graph.add_node("execute", execute)
    graph.add_node("prepare_correction", prepare_correction)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", "validate")
    graph.add_conditional_edges(
        "validate",
        route_failed_state,
        {"correct": "prepare_correction", "failure": END, "success": "execute"},
    )
    graph.add_conditional_edges(
        "execute",
        route_failed_state,
        {"correct": "prepare_correction", "failure": END, "success": END},
    )
    graph.add_edge("prepare_correction", "generate")
    return graph.compile()


def _run_graph(
    schema: DatabaseSchema,
    question: str,
    generator: CorrectingSQLGenerator,
    schema_selector: SchemaSelector,
    execute_query: Callable[[str], tuple[tuple[str, ...], tuple[tuple[Any, ...], ...]]],
    question_resolver: QuestionResolver | None,
    max_retries: int,
    progress_callback: Callable[[str], None] | None,
    execution_label: str,
) -> tuple[dict[str, Any], str | None]:
    """Resolve and invoke the shared graph for any read-only execution boundary."""
    _report_progress(progress_callback, "Checking whether the question is answerable...")
    resolution = question_resolver.resolve(schema, question) if question_resolver else None
    if resolution is not None and resolution.kind == "clarification":
        return {
            "status": "clarification",
            "question": question,
            "sql": None,
            "retry_count": 0,
            "latency_ms": 0,
            "clarification": resolution.message,
        }, None
    if resolution is not None and resolution.kind == "no_answer":
        return {
            "status": "no_answer",
            "question": question,
            "sql": None,
            "retry_count": 0,
            "latency_ms": 0,
            "no_answer": resolution.message,
        }, None
    graph = _build_graph(
        execute_query, generator, schema_selector, progress_callback, execution_label
    )
    return graph.invoke(
        {
            "question": question,
            "schema": schema,
            "correction": None,
            "retry_count": 0,
            "max_retries": max_retries,
        },
        config={"recursion_limit": max(25, (max_retries + 1) * _GRAPH_STEPS_PER_ATTEMPT)},
    ), resolution.message if resolution is not None else None


def _duckdb_result(
    connection: duckdb.DuckDBPyConnection, sql: str
) -> tuple[tuple[str, ...], tuple[tuple[Any, ...], ...]]:
    cursor = execute_read_only(connection, sql)
    return tuple(description[0] for description in cursor.description or ()), tuple(
        tuple(row) for row in cursor.fetchall()
    )


def _adapter_result(result: Any) -> tuple[tuple[str, ...], tuple[tuple[Any, ...], ...]]:
    """Normalize the adapter's bounded result into the graph's internal shape."""
    return result.columns, result.rows


def _normalize_question(question: str) -> str:
    if not isinstance(question, str):
        raise TypeError("question must be a string")
    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("question must be a non-empty string")
    return normalized_question


def _validate_max_retries(max_retries: int) -> None:
    if type(max_retries) is not int or not 0 <= max_retries <= MAX_RETRIES:
        raise ValueError(f"max_retries must be an integer between 0 and {MAX_RETRIES}")


def _report_progress(callback: Callable[[str], None] | None, message: str) -> None:
    """Send a safe operational status update to an optional interactive caller."""
    if callback is not None:
        callback(message)


def _build_exhaustion_explanation(retry_count: int) -> str:
    attempts = retry_count + 1
    label = "attempt" if attempts == 1 else "attempts"
    return f"Could not produce executable read-only SQL after {attempts} {label}."


def _elapsed_ms(started_at: float) -> float:
    return (perf_counter() - started_at) * 1000
