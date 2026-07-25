"""FastAPI boundary for the safe Queris agent pipeline."""

import json
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any, Literal
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, StringConstraints

from queris.agent_loop import AgentQueryResult, CorrectingSQLGenerator, run_agent_loop
from queris.generation import GeminiSQLGenerator, SQLGenerationError
from queris.pipeline import FullSchemaSelector
from queris.query_sources import QuerySource

DEFAULT_DATABASE_PATH = Path("data/retail.duckdb")
LOGGER = logging.getLogger("queris.api")
LOGGED_ROUTES = frozenset({"/health", "/query"})
NonEmptyQuestion = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
GeneratorFactory = Callable[[], CorrectingSQLGenerator]
RequestHandler = Callable[[Request], Awaitable[Response]]


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
    logger: logging.Logger = LOGGER,
) -> FastAPI:
    """Create a configured API application with injectable generation."""
    configured_database = Path(
        database_path
        if database_path is not None
        else os.getenv("QUERIS_DATABASE", str(DEFAULT_DATABASE_PATH))
    )
    application = FastAPI(title="Queris API", version="0.1.0")

    @application.middleware("http")
    async def log_request(request: Request, call_next: RequestHandler) -> Response:
        request_id = str(uuid4())
        started_at = perf_counter()
        response_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        request.state.query_decision = "not_applicable"
        request.state.retry_count = None
        request.state.blocked = None
        request.state.agent_latency_ms = None
        try:
            response = await call_next(request)
            response_status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            request.state.query_decision = "error"
            raise
        finally:
            logger.info(
                json.dumps(
                    {
                        "event": "http.request.completed",
                        "request_id": request_id,
                        "method": request.method,
                        "route": (
                            request.url.path if request.url.path in LOGGED_ROUTES else "unmatched"
                        ),
                        "status_code": response_status,
                        "latency_ms": round((perf_counter() - started_at) * 1000, 3),
                        "query_decision": request.state.query_decision,
                        "retry_count": request.state.retry_count,
                        "blocked": request.state.blocked,
                        "agent_latency_ms": request.state.agent_latency_ms,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        available = configured_database.is_file()
        return HealthResponse(
            status="ok" if available else "degraded",
            database_available=available,
        )

    @application.post("/query", response_model=QueryResponse)
    async def query(request: QueryRequest, http_request: Request) -> QueryResponse:
        if not configured_database.is_file():
            http_request.state.query_decision = "unavailable"
            http_request.state.retry_count = 0
            http_request.state.blocked = False
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
            http_request.state.query_decision = "unavailable"
            http_request.state.retry_count = 0
            http_request.state.blocked = False
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error
        if result.blocked:
            http_request.state.query_decision = "blocked"
        elif result.status == "success":
            http_request.state.query_decision = "allowed"
        else:
            http_request.state.query_decision = "not_executed"
        http_request.state.retry_count = result.retry_count
        http_request.state.blocked = result.blocked
        http_request.state.agent_latency_ms = round(result.latency_ms, 3)
        return QueryResponse.from_agent_result(result)

    return application


app = create_app()


def _configure_service_logging() -> None:
    if not LOGGER.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def main() -> None:
    """Run the local API server with environment-based binding."""
    _configure_service_logging()
    uvicorn.run(
        "queris.api:app",
        host=os.getenv("QUERIS_HOST", "127.0.0.1"),
        port=int(os.getenv("QUERIS_PORT", "8000")),
    )
