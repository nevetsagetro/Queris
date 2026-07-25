import json
import logging
from pathlib import Path
from uuid import UUID

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


def request_log(caplog: pytest.LogCaptureFixture) -> dict[str, object]:
    [record] = [
        record
        for record in caplog.records
        if record.name == "queris.api" and record.getMessage().startswith("{")
    ]
    return json.loads(record.getMessage())


@pytest.mark.anyio
async def test_health_reports_database_readiness(sample_database: Path) -> None:
    async with api_client(create_app(database_path=sample_database)) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database_available": True}


@pytest.mark.anyio
async def test_query_returns_typed_safe_agent_result(
    sample_database: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    question = "How many secret orders are there?"
    app = create_app(
        database_path=sample_database,
        generator_factory=lambda: StaticGenerator("SELECT COUNT(*) AS order_count FROM orders"),
    )
    with caplog.at_level(logging.INFO, logger="queris.api"):
        async with api_client(app) as client:
            response = await client.post("/query", json={"question": f"  {question}  "})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["question"] == question
    assert payload["sql"] == "SELECT COUNT(*) AS order_count FROM orders"
    assert payload["columns"] == ["order_count"]
    assert payload["rows"] == [[4]]
    assert payload["sources"] == [{"schema_name": "main", "table_name": "orders", "columns": ["*"]}]
    assert payload["retry_count"] == 0
    assert payload["latency_ms"] >= 0
    assert payload["blocked"] is False
    log = request_log(caplog)
    UUID(response.headers["X-Request-ID"])
    assert log["request_id"] == response.headers["X-Request-ID"]
    assert log["route"] == "/query"
    assert log["status_code"] == 200
    assert log["query_decision"] == "allowed"
    assert log["retry_count"] == 0
    assert log["blocked"] is False
    assert log["agent_latency_ms"] >= 0
    assert log["latency_ms"] >= log["agent_latency_ms"]
    assert question not in caplog.text
    assert payload["sql"] not in caplog.text


@pytest.mark.anyio
async def test_query_surfaces_terminal_validation_block(
    sample_database: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(
        database_path=sample_database,
        generator_factory=lambda: StaticGenerator("DELETE FROM orders"),
    )
    with caplog.at_level(logging.INFO, logger="queris.api"):
        async with api_client(app) as client:
            response = await client.post("/query", json={"question": "Delete every order"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failure"
    assert payload["failure_stage"] == "validation"
    assert payload["blocked"] is True
    assert payload["retry_count"] == 3
    assert payload["rows"] == []
    log = request_log(caplog)
    assert log["query_decision"] == "blocked"
    assert log["retry_count"] == 3
    assert log["blocked"] is True
    assert "Delete every order" not in caplog.text
    assert "DELETE FROM orders" not in caplog.text


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
