"""Session-scoped audit history for the Streamlit demo."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from queris.agent_loop import AgentQueryResult
from queris.query_sources import QuerySource


class SessionQuery(BaseModel):
    """One successful query retained for the lifetime of a demo session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str
    status: Literal["success", "failure", "clarification", "no_answer"]
    sql: str | None
    sources: tuple[QuerySource, ...]
    retry_count: int = Field(ge=0)
    latency_ms: float = Field(ge=0)
    blocked: bool


def session_query_from_result(result: AgentQueryResult) -> SessionQuery:
    """Create an auditable session record from one terminal agent result."""
    return SessionQuery(
        question=result.question,
        status=result.status,
        sql=result.sql,
        sources=result.sources,
        retry_count=result.retry_count,
        latency_ms=result.latency_ms,
        blocked=result.blocked,
    )


def format_query_source(source: QuerySource) -> str:
    """Render one table and its referenced columns for the demo history."""
    columns = ", ".join(source.columns) if source.columns else "(no direct column reference)"
    return f"{source.schema_name}.{source.table_name}: {columns}"
