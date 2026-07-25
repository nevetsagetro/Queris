"""Session-scoped audit history for the Streamlit demo."""

from pydantic import BaseModel, ConfigDict

from queris.agent_loop import AgentQueryResult
from queris.query_sources import QuerySource


class SessionQuery(BaseModel):
    """One successful query retained for the lifetime of a demo session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str
    sql: str
    sources: tuple[QuerySource, ...]


def session_query_from_result(result: AgentQueryResult) -> SessionQuery:
    """Create an auditable session record from a successful agent result."""
    if result.status != "success" or result.sql is None:
        raise ValueError("only successful query results can be recorded")
    return SessionQuery(
        question=result.question,
        sql=result.sql,
        sources=result.sources,
    )


def format_query_source(source: QuerySource) -> str:
    """Render one table and its referenced columns for the demo history."""
    columns = ", ".join(source.columns) if source.columns else "(no direct column reference)"
    return f"{source.schema_name}.{source.table_name}: {columns}"
