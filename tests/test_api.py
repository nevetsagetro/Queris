import json
import logging
from pathlib import Path
from uuid import UUID

import duckdb
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
async def test_catalog_and_examples_are_discoverable(sample_database: Path) -> None:
    async with api_client(create_app(database_path=sample_database)) as client:
        catalog = await client.get("/catalog")
        datasets = await client.get("/datasets")
        profile = await client.get("/catalog/profile")
        enrichment = await client.get("/catalog/enrichment")
        recommendations = await client.get("/recommendations")
        language = await client.post(
            "/language/similarity",
            json={"question": "How many customers were there in December?"},
        )
        examples = await client.get("/examples")
        demo_history = await client.get("/history/demo")

    assert catalog.status_code == 200
    assert datasets.status_code == 200
    assert any(item["active"] for item in datasets.json())
    assert profile.status_code == 200
    assert profile.json()["source"] == "read_only_profile"
    assert enrichment.status_code == 200
    assert enrichment.json()["status"] in {"raw", "approved", "stale"}
    assert recommendations.status_code == 200
    assert recommendations.json()
    assert language.status_code == 200
    assert language.json()["intent"]["entity"] == "customer"
    assert language.json()["intent"]["filters"] == ["december"]
    assert catalog.json()["table_count"] == 5
    assert {table["name"] for table in catalog.json()["tables"]} == {
        "categories",
        "order_items",
        "orders",
        "products",
        "regions",
    }
    assert examples.status_code == 200
    assert len(examples.json()) == 100
    assert examples.json()[0]["question"]
    assert demo_history.status_code == 200
    assert len(demo_history.json()) == 100
    assert demo_history.json()[0]["status"] == "ready_to_run"
    assert demo_history.json()[0]["source"] == "demo"


@pytest.mark.anyio
async def test_non_retail_dataset_gets_schema_specific_starters(tmp_path: Path) -> None:
    database = tmp_path / "penguins.duckdb"
    connection = duckdb.connect(str(database))
    connection.execute(
        "CREATE TABLE penguins (species VARCHAR, body_mass_g INTEGER, island VARCHAR, year INTEGER)"
    )
    connection.execute(
        "INSERT INTO penguins VALUES "
        "('Adelie', 3700, 'Dream', 2007), ('Gentoo', 5000, 'Biscoe', 2008)"
    )
    connection.close()

    async with api_client(create_app(database_path=database)) as client:
        examples = await client.get("/examples")
        demo_history = await client.get("/history/demo")
        catalog = await client.get("/catalog")
        recommendations = await client.get("/recommendations")
        demo = await client.post(
            "/query",
            json={
                "question": "How many penguins are there by species?",
                "demo_id": "penguins-species-count",
            },
        )

    assert examples.status_code == 200
    assert len(examples.json()) >= 12
    assert examples.json()[0]["question"] == "How many penguins are there by species?"
    assert demo_history.status_code == 200
    assert len(demo_history.json()) >= 12
    assert demo_history.json()[0]["id"] == "history-penguins-species-count"
    assert catalog.json()["table_count"] == 1
    assert recommendations.json()[0]["demo_id"] == "penguins-species-count"
    assert demo.json()["execution_mode"] == "demo"
    assert {tuple(row) for row in demo.json()["rows"]} == {("Adelie", 1), ("Gentoo", 1)}


@pytest.mark.anyio
async def test_query_reuses_api_cache(
    sample_database: Path,
) -> None:
    calls = 0

    def generator_factory() -> StaticGenerator:
        nonlocal calls
        calls += 1
        return StaticGenerator("SELECT COUNT(*) AS order_count FROM orders")

    app = create_app(database_path=sample_database, generator_factory=generator_factory)
    async with api_client(app) as client:
        first = await client.post("/query", json={"question": "How many orders?"})
        second = await client.post("/query", json={"question": "  how many   ORDERS? "})

    assert first.json()["cache_hit"] is False
    assert second.json()["cache_hit"] is True
    assert calls == 1


@pytest.mark.anyio
async def test_demo_query_uses_prepared_sql_without_generator(
    sample_database: Path,
) -> None:
    def generator_factory() -> StaticGenerator:
        raise AssertionError("demo queries must not construct an LLM generator")

    app = create_app(database_path=sample_database, generator_factory=generator_factory)
    async with api_client(app) as client:
        response = await client.post(
            "/query",
            json={
                "question": "What was total revenue by country?",
                "demo_id": "revenue-01",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_mode"] == "demo"
    assert payload["cache_hit"] is False
    assert payload["status"] == "success"
    assert payload["rows"]


@pytest.mark.anyio
async def test_stale_generic_demo_id_cannot_execute_the_wrong_question(
    sample_database: Path,
) -> None:
    def generator_factory() -> StaticGenerator:
        return StaticGenerator("SELECT COUNT(*) AS order_count FROM orders")

    app = create_app(database_path=sample_database, generator_factory=generator_factory)
    async with api_client(app) as client:
        response = await client.post(
            "/query",
            json={
                "question": "What was total revenue for orders above the median order value?",
                "demo_id": "table-count:penguins",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_mode"] == "llm"
    assert payload["sql"] == "SELECT COUNT(*) AS order_count FROM orders"


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
