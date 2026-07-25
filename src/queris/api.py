"""FastAPI boundary for the safe Queris agent pipeline."""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, StringConstraints

from queris.agent_loop import AgentQueryResult, CorrectingSQLGenerator, run_agent_loop
from queris.generation import GeminiSQLGenerator, SQLGenerationError
from queris.pipeline import FullSchemaSelector
from queris.query_sources import QuerySource

DEFAULT_DATABASE_PATH = Path("data/retail.duckdb")
NonEmptyQuestion = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
GeneratorFactory = Callable[[], CorrectingSQLGenerator]


class HealthResponse(BaseModel):
    """Service health without exposing configuration details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok", "degraded"]
    database_available: bool


class QueryRequest(BaseModel):
    """One natural-language analytics request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: NonEmptyQuestion


class QueryResponse(BaseModel):
    """One typed terminal response from the safe agent loop."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["success", "failure", "clarification", "no_answer"]
    question: str
    sql: str | None
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    sources: tuple[QuerySource, ...]
    retry_count: int
    latency_ms: float
    blocked: bool
    failure_stage: str | None
    error: str | None
    explanation: str | None
    clarification: str | None
    assumption: str | None
    no_answer: str | None

    @classmethod
    def from_agent_result(cls, result: AgentQueryResult) -> "QueryResponse":
        """Map the internal result to the stable HTTP response contract."""
        return cls(
            status=result.status,
            question=result.question,
            sql=result.sql,
            columns=result.columns,
            rows=result.rows,
            sources=result.sources,
            retry_count=result.retry_count,
            latency_ms=result.latency_ms,
            blocked=result.blocked,
            failure_stage=result.failure_stage,
            error=result.error,
            explanation=result.explanation,
            clarification=result.clarification,
            assumption=result.assumption,
            no_answer=result.no_answer,
        )


def create_app(
    *,
    database_path: str | Path | None = None,
    generator_factory: GeneratorFactory = GeminiSQLGenerator,
) -> FastAPI:
    """Create a configured API application with injectable generation."""
    configured_database = Path(
        database_path
        if database_path is not None
        else os.getenv("QUERIS_DATABASE", str(DEFAULT_DATABASE_PATH))
    )
    application = FastAPI(title="Queris API", version="0.1.0")

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        available = configured_database.is_file()
        return HealthResponse(
            status="ok" if available else "degraded",
            database_available=available,
        )

    @application.post("/query", response_model=QueryResponse)
    async def query(request: QueryRequest) -> QueryResponse:
        if not configured_database.is_file():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Configured database is unavailable",
            )
        try:
            result = run_agent_loop(
                configured_database,
                request.question,
                generator_factory(),
                FullSchemaSelector(),
            )
        except SQLGenerationError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error
        return QueryResponse.from_agent_result(result)

    return application


app = create_app()


def main() -> None:
    """Run the local API server with environment-based binding."""
    uvicorn.run(
        "queris.api:app",
        host=os.getenv("QUERIS_HOST", "127.0.0.1"),
        port=int(os.getenv("QUERIS_PORT", "8000")),
    )
