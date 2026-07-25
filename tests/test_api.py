from pathlib import Path

import httpx
import pytest

from queris.api import create_app
from queris.generation import SQLCorrectionContext
from queris.schema import DatabaseSchema


class StaticGenerator:
    def __init__(self, sql: str) -> None:
        self.sql = sql

    def generate_sql(
        self,
        schema: DatabaseSchema,
        question: str,
        correction: SQLCorrectionContext | None = None,
    ) -> str:
        return self.sql


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def api_client(app: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.mark.anyio
async def test_health_reports_database_readiness(sample_database: Path) -> None:
    async with api_client(create_app(database_path=sample_database)) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database_available": True}


@pytest.mark.anyio
async def test_query_returns_typed_safe_agent_result(sample_database: Path) -> None:
    app = create_app(
        database_path=sample_database,
        generator_factory=lambda: StaticGenerator("SELECT COUNT(*) AS order_count FROM orders"),
    )
    async with api_client(app) as client:
        response = await client.post("/query", json={"question": "  How many orders are there?  "})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["question"] == "How many orders are there?"
    assert payload["sql"] == "SELECT COUNT(*) AS order_count FROM orders"
    assert payload["columns"] == ["order_count"]
    assert payload["rows"] == [[4]]
    assert payload["sources"] == [{"schema_name": "main", "table_name": "orders", "columns": ["*"]}]
    assert payload["retry_count"] == 0
    assert payload["latency_ms"] >= 0
    assert payload["blocked"] is False


@pytest.mark.anyio
async def test_query_surfaces_terminal_validation_block(sample_database: Path) -> None:
    app = create_app(
        database_path=sample_database,
        generator_factory=lambda: StaticGenerator("DELETE FROM orders"),
    )
    async with api_client(app) as client:
        response = await client.post("/query", json={"question": "Delete every order"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failure"
    assert payload["failure_stage"] == "validation"
    assert payload["blocked"] is True
    assert payload["retry_count"] == 3
    assert payload["rows"] == []


@pytest.mark.anyio
async def test_query_rejects_empty_question(sample_database: Path) -> None:
    async with api_client(create_app(database_path=sample_database)) as client:
        response = await client.post("/query", json={"question": "  "})

    assert response.status_code == 422


@pytest.mark.anyio
async def test_missing_database_is_degraded_and_unavailable(tmp_path: Path) -> None:
    app = create_app(database_path=tmp_path / "missing.duckdb")
    async with api_client(app) as client:
        health = await client.get("/health")
        query = await client.post("/query", json={"question": "How many orders?"})

    assert health.json() == {"status": "degraded", "database_available": False}
    assert query.status_code == 503
    assert query.json() == {"detail": "Configured database is unavailable"}
