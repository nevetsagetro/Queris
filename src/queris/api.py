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
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, StringConstraints

from queris.agent_loop import AgentQueryResult, CorrectingSQLGenerator, run_agent_loop
from queris.catalog_enrichment import EnrichmentStatus, enrich_schema
from queris.catalog_profile import CatalogProfile, profile_database
from queris.chart_recommender import ChartRecommendation, recommend_chart
from queris.dataset_demos import get_dataset_demo, get_dataset_demos
from queris.datasets import DatasetInfo, discover_datasets, select_dataset
from queris.demo_cache import cache_result, cached_result, load_schema_catalog
from queris.demo_examples import DemoExample, DemoHistoryItem, get_demo_examples, get_demo_history
from queris.demo_runner import demo_definition, run_demo_query, run_prepared_query
from queris.generation import GeminiSQLGenerator, SQLGenerationError
from queris.language_similarity import (
    QuestionIntent,
    SimilarQuestion,
    analyze_question,
    find_similar_questions,
    prompt_context,
)
from queris.pipeline import FullSchemaSelector
from queris.query_sources import QuerySource
from queris.recommendations import RecommendedRun, recommend_runs
from queris.schema import DatabaseSchema, TableSchema

DEFAULT_DATABASE_PATH = Path("data/retail.duckdb")
LOGGER = logging.getLogger("queris.api")
LOGGED_ROUTES = frozenset(
    {
        "/health",
        "/datasets",
        "/datasets/select",
        "/catalog",
        "/catalog/profile",
        "/catalog/enrichment",
        "/recommendations",
        "/language/similarity",
        "/examples",
        "/history/demo",
        "/query",
        "/query/replay",
    }
)
NonEmptyQuestion = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
GeneratorFactory = Callable[[], CorrectingSQLGenerator]
RequestHandler = Callable[[Request], Awaitable[Response]]


class SimilarityAwareGenerator:
    """Decorate a generator with curated, explicitly untrusted prompt context."""

    def __init__(
        self, generator: CorrectingSQLGenerator, similar_questions: tuple[SimilarQuestion, ...]
    ):
        self.generator = generator
        self.context = prompt_context(similar_questions)

    def generate_sql(self, schema: DatabaseSchema, question: str, correction: Any = None) -> str:
        return self.generator.generate_sql(schema, question + self.context, correction)


class HealthResponse(BaseModel):
    """Service health without exposing configuration details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok", "degraded"]
    database_available: bool


class QueryRequest(BaseModel):
    """One natural-language analytics request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: NonEmptyQuestion
    demo_id: str | None = None


class ReplayQueryRequest(BaseModel):
    """Previously validated question and SQL to execute without an LLM."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: NonEmptyQuestion
    sql: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DatasetSelectionRequest(BaseModel):
    """Select one discovered local dataset by its filename id."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class LanguageSimilarityRequest(BaseModel):
    """Question submitted for local intent and similarity analysis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: NonEmptyQuestion


class LanguageAnalysisResponse(BaseModel):
    """Local intent interpretation and similar validated question patterns."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: QuestionIntent
    similar_questions: tuple[SimilarQuestion, ...]


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
    cache_hit: bool = False
    execution_mode: Literal["llm", "cache", "demo"] = "llm"
    chart_recommendation: ChartRecommendation | None = None
    similar_questions: tuple[SimilarQuestion, ...] = ()

    @classmethod
    def from_agent_result(
        cls,
        result: AgentQueryResult,
        *,
        cache_hit: bool = False,
        execution_mode: Literal["llm", "cache", "demo"] = "llm",
        similar_questions: tuple[SimilarQuestion, ...] = (),
    ) -> "QueryResponse":
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
            cache_hit=cache_hit,
            execution_mode=execution_mode,
            chart_recommendation=(
                recommend_chart(result.columns, result.rows) if result.status == "success" else None
            ),
            similar_questions=similar_questions,
        )


class CatalogResponse(BaseModel):
    """Safe schema discovery response for frontend clients."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["session"]
    table_count: int
    tables: tuple[TableSchema, ...]


class CatalogEnrichmentResponse(EnrichmentStatus):
    """Enrichment status for the active dataset."""


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
    dataset_directory = (
        Path(os.getenv("QUERIS_DATABASE_DIR", str(configured_database.parent)))
        .expanduser()
        .resolve()
    )
    active_database = configured_database.expanduser().resolve()
    metadata_directory = Path(os.getenv("QUERIS_METADATA_DIR", "metadata")).expanduser().resolve()
    application = FastAPI(title="Queris API", version="0.1.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )
    query_cache: dict[str, AgentQueryResult] = {}
    schema_cache: dict[str, DatabaseSchema] = {}
    profile_cache: dict[str, CatalogProfile] = {}

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
        available = active_database.is_file()
        return HealthResponse(
            status="ok" if available else "degraded",
            database_available=available,
        )

    @application.get("/datasets", response_model=tuple[DatasetInfo, ...])
    async def datasets() -> tuple[DatasetInfo, ...]:
        return discover_datasets(dataset_directory, active_database, metadata_directory)

    @application.post("/datasets/select", response_model=tuple[DatasetInfo, ...])
    async def select_dataset_route(request: DatasetSelectionRequest) -> tuple[DatasetInfo, ...]:
        nonlocal active_database
        try:
            active_database = select_dataset(dataset_directory, request.dataset_id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        query_cache.clear()
        schema_cache.clear()
        profile_cache.clear()
        return discover_datasets(dataset_directory, active_database, metadata_directory)

    def active_schema_and_enrichment() -> tuple[DatabaseSchema, EnrichmentStatus]:
        raw_schema = load_schema_catalog(schema_cache, active_database)
        return enrich_schema(raw_schema, active_database, metadata_directory)

    @application.get("/catalog", response_model=CatalogResponse)
    async def catalog() -> CatalogResponse:
        if not active_database.is_file():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Configured database is unavailable",
            )
        schema, _ = active_schema_and_enrichment()
        return CatalogResponse(
            source="session",
            table_count=len(schema.tables),
            tables=schema.tables,
        )

    @application.get("/catalog/enrichment", response_model=CatalogEnrichmentResponse)
    async def catalog_enrichment() -> CatalogEnrichmentResponse:
        if not active_database.is_file():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Configured database is unavailable",
            )
        _, enrichment = active_schema_and_enrichment()
        return CatalogEnrichmentResponse(**enrichment.model_dump())

    @application.get("/recommendations", response_model=tuple[RecommendedRun, ...])
    async def recommendations() -> tuple[RecommendedRun, ...]:
        if not active_database.is_file():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Configured database is unavailable",
            )
        schema, _ = active_schema_and_enrichment()
        return recommend_runs(schema, limit=50)

    @application.post("/language/similarity", response_model=LanguageAnalysisResponse)
    async def language_similarity(request: LanguageSimilarityRequest) -> LanguageAnalysisResponse:
        return LanguageAnalysisResponse(
            intent=analyze_question(request.question),
            similar_questions=find_similar_questions(request.question),
        )

    @application.get("/examples", response_model=tuple[DemoExample, ...])
    async def examples() -> tuple[DemoExample, ...]:
        if not active_database.is_file():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Configured database is unavailable",
            )
        schema, _ = active_schema_and_enrichment()
        return _dataset_examples(schema)

    @application.get("/catalog/profile", response_model=CatalogProfile)
    async def catalog_profile() -> CatalogProfile:
        if not active_database.is_file():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Configured database is unavailable",
            )
        stat = active_database.stat()
        cache_key = f"{active_database}:{stat.st_mtime_ns}:{stat.st_size}"
        if cache_key not in profile_cache:
            profile_cache[cache_key] = profile_database(str(active_database))
        return profile_cache[cache_key]

    @application.get("/history/demo", response_model=tuple[DemoHistoryItem, ...])
    async def demo_history() -> tuple[DemoHistoryItem, ...]:
        if not active_database.is_file():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Configured database is unavailable",
            )
        schema, _ = active_schema_and_enrichment()
        return _dataset_demo_history(schema)

    @application.post("/query", response_model=QueryResponse)
    async def query(request: QueryRequest, http_request: Request) -> QueryResponse:
        if not active_database.is_file():
            http_request.state.query_decision = "unavailable"
            http_request.state.retry_count = 0
            http_request.state.blocked = False
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Configured database is unavailable",
            )
        cached = cached_result(query_cache, active_database, request.question)
        cache_hit = cached is not None
        prepared_demo = demo_definition(request.demo_id) if request.demo_id else None
        if prepared_demo is not None and not _questions_match(
            request.question, prepared_demo.example.question
        ):
            prepared_demo = None
        similar_questions = find_similar_questions(request.question)
        try:
            active_schema = active_schema_and_enrichment()[0]
            prepared_dataset_demo = get_dataset_demo(active_schema, request.demo_id)
            if prepared_dataset_demo is not None and not _questions_match(
                request.question, prepared_dataset_demo.question
            ):
                prepared_dataset_demo = None
            generic_recommendation = (
                _generic_recommendation(request.demo_id) if request.demo_id else None
            )
            if generic_recommendation is not None and not _questions_match(
                request.question, f"How many rows are in {generic_recommendation}?"
            ):
                generic_recommendation = None
            if cached is not None:
                result = cached
                execution_mode = "cache"
            elif prepared_demo is not None:
                result = run_demo_query(active_database, prepared_demo)
                execution_mode = "demo"
            elif prepared_dataset_demo is not None:
                result = run_prepared_query(
                    active_database,
                    request.question,
                    prepared_dataset_demo.sql,
                )
                execution_mode = "demo"
            elif generic_recommendation is not None:
                table_name = generic_recommendation
                if table_name not in {table.name for table in active_schema.tables}:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Unknown prepared recommendation",
                    )
                escaped_table = table_name.replace('"', '""')
                result = run_prepared_query(
                    active_database,
                    request.question,
                    f'SELECT COUNT(*) AS row_count FROM "{escaped_table}"',
                )
                execution_mode = "demo"
            else:
                generator = SimilarityAwareGenerator(generator_factory(), similar_questions)
                result = run_agent_loop(
                    active_database,
                    request.question,
                    generator,
                    FullSchemaSelector(),
                    schema_override=active_schema_and_enrichment()[0],
                )
                execution_mode = "llm"
        except SQLGenerationError as error:
            http_request.state.query_decision = "unavailable"
            http_request.state.retry_count = 0
            http_request.state.blocked = False
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error
        if not cache_hit:
            cache_result(query_cache, active_database, request.question, result)
        if result.blocked:
            http_request.state.query_decision = "blocked"
        elif result.status == "success":
            http_request.state.query_decision = "allowed"
        else:
            http_request.state.query_decision = "not_executed"
        http_request.state.retry_count = result.retry_count
        http_request.state.blocked = result.blocked
        http_request.state.agent_latency_ms = round(result.latency_ms, 3)
        return QueryResponse.from_agent_result(
            result,
            cache_hit=cache_hit,
            execution_mode=execution_mode,
            similar_questions=similar_questions,
        )

    @application.post("/query/replay", response_model=QueryResponse)
    async def replay_query(request: ReplayQueryRequest, http_request: Request) -> QueryResponse:
        """Replay saved read-only SQL without constructing or calling an LLM."""
        if not active_database.is_file():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Configured database is unavailable",
            )
        try:
            result = run_prepared_query(active_database, request.question, request.sql)
        except ValueError as error:
            http_request.state.query_decision = "not_executed"
            http_request.state.retry_count = 0
            http_request.state.blocked = False
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
            ) from error
        http_request.state.query_decision = "allowed"
        http_request.state.retry_count = 0
        http_request.state.blocked = False
        http_request.state.agent_latency_ms = round(result.latency_ms, 3)
        return QueryResponse.from_agent_result(
            result,
            cache_hit=True,
            execution_mode="cache",
        )

    return application


def _generic_recommendation(demo_id: str | None) -> str | None:
    """Parse only the server-generated generic recommendation namespace."""
    if not demo_id or not demo_id.startswith("table-count:"):
        return None
    table_name = demo_id.removeprefix("table-count:")
    return table_name if table_name and ":" not in table_name else None


def _questions_match(left: str, right: str) -> bool:
    """Accept harmless whitespace/case changes, but reject stale demo contexts."""
    return " ".join(left.casefold().split()) == " ".join(right.casefold().split())


def _dataset_examples(schema: DatabaseSchema) -> tuple[DemoExample, ...]:
    """Return starters that belong to the active schema, not a previous dataset."""
    if _is_retail_schema(schema):
        return get_demo_examples()
    return tuple(
        DemoExample(
            id=demo.id,
            title=demo.question,
            question=demo.question,
            category="discovery",
            tables=demo.tables,
            chart=demo.chart,
        )
        for demo in get_dataset_demos(schema)
    )


def _dataset_demo_history(schema: DatabaseSchema) -> tuple[DemoHistoryItem, ...]:
    """Expose a demo-history layer for every schema, including generated starters."""
    if _is_retail_schema(schema):
        return get_demo_history()
    return tuple(
        DemoHistoryItem(
            id=f"history-{demo.id}",
            source="demo",
            created_at="2026-01-01T00:00:00Z",
            user="Queris catalog",
            question=demo.question,
            status="ready_to_run",
            tables=demo.tables,
            chart=demo.chart,
            explanation="Deterministic starter generated from the active dataset catalog.",
            result_summary=demo.reason,
        )
        for demo in get_dataset_demos(schema)
    )


def _is_retail_schema(schema: DatabaseSchema) -> bool:
    """Identify the normalized retail shape that owns the curated 100-question history."""
    table_names = {table.name for table in schema.tables}
    return {"orders", "order_items"}.issubset(table_names)


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
