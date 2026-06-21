"""Typed LangGraph foundation for bounded text-to-SQL orchestration."""

from pathlib import Path
from typing import Any, Literal, NotRequired, Protocol, Self, TypedDict

import duckdb
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, model_validator

from queris.database import execute_read_only, read_only_connection
from queris.generation import SQLCorrectionContext
from queris.pipeline import SchemaSelector
from queris.schema import DatabaseSchema, introspect_schema
from queris.sql_validation import SQLValidationError, parse_read_only

FailureStage = Literal["validation", "execution"]


class CorrectingSQLGenerator(Protocol):
    """Generate initial SQL and corrections from failed-attempt context."""

    def generate_sql(
        self,
        schema: DatabaseSchema,
        question: str,
        correction: SQLCorrectionContext | None = None,
    ) -> str: ...


class AgentQueryResult(BaseModel):
    """Terminal success or failure from one graph execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["success", "failure"]
    question: str
    sql: str
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    failure_stage: FailureStage | None = None
    error: str | None = None

    @model_validator(mode="after")
    def require_consistent_terminal_state(self) -> Self:
        if self.status == "success" and (self.failure_stage is not None or self.error is not None):
            raise ValueError("successful result must not contain failure details")
        if self.status == "failure" and (self.failure_stage is None or not self.error):
            raise ValueError("failed result must contain failure details")
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
    correction_attempted: NotRequired[bool]


def run_agent_loop(
    database_path: str | Path,
    question: str,
    generator: CorrectingSQLGenerator,
    schema_selector: SchemaSelector,
    *,
    sample_limit: int = 3,
) -> AgentQueryResult:
    """Run generate, validate, execute, and at most one correction pass."""
    normalized_question = _normalize_question(question)

    with read_only_connection(database_path) as connection:
        schema = introspect_schema(connection, sample_limit=sample_limit)
        graph = _build_graph(connection, generator, schema_selector)
        state = graph.invoke(
            {
                "question": normalized_question,
                "schema": schema,
                "correction": None,
                "correction_attempted": False,
            }
        )

    return AgentQueryResult(
        status=state["status"],
        question=normalized_question,
        sql=state["sql"],
        columns=state.get("columns", ()),
        rows=state.get("rows", ()),
        failure_stage=state.get("failure_stage"),
        error=state.get("error"),
    )


def _build_graph(
    connection: duckdb.DuckDBPyConnection,
    generator: CorrectingSQLGenerator,
    schema_selector: SchemaSelector,
) -> CompiledStateGraph[_AgentState, None, _AgentState, _AgentState]:
    def generate(state: _AgentState) -> dict[str, object]:
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
        try:
            cursor = execute_read_only(connection, state["sql"])
        except SQLValidationError as error:
            return {
                "status": "failure",
                "failure_stage": "validation",
                "error": str(error),
            }
        except duckdb.Error as error:
            return {
                "status": "failure",
                "failure_stage": "execution",
                "error": str(error),
            }
        return {
            "status": "success",
            "columns": tuple(description[0] for description in cursor.description or ()),
            "rows": tuple(tuple(row) for row in cursor.fetchall()),
        }

    def prepare_correction(state: _AgentState) -> dict[str, object]:
        failure_stage = state.get("failure_stage")
        error = state.get("error")
        if failure_stage is None or error is None:
            raise RuntimeError("failed graph state is missing correction diagnostics")
        return {
            "correction": SQLCorrectionContext(
                previous_sql=state["sql"],
                failure_stage=failure_stage,
                error=error,
            ),
            "correction_attempted": True,
        }

    def route_failed_state(state: _AgentState) -> str:
        if state.get("status") != "failure":
            return "success"
        return "failure" if state.get("correction_attempted", False) else "correct"

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


def _normalize_question(question: str) -> str:
    if not isinstance(question, str):
        raise TypeError("question must be a string")
    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("question must be a non-empty string")
    return normalized_question
