from pathlib import Path

from queris.agent_loop import AgentQueryResult
from queris.demo_cache import (
    cache_result,
    cached_result,
    load_schema_catalog,
    query_cache_key,
)


def _result(question: str) -> AgentQueryResult:
    return AgentQueryResult(
        status="success",
        question=question,
        sql="SELECT 1",
        columns=("value",),
        rows=((1,),),
        retry_count=0,
    )


def test_query_cache_reuses_normalized_question(tmp_path: Path) -> None:
    database = tmp_path / "retail.duckdb"
    database.write_bytes(b"database")
    cache: dict[str, AgentQueryResult] = {}
    result = _result("Average price by category")

    cache_result(cache, database, result.question, result)

    assert cached_result(cache, database, "  average   PRICE by category ") == result


def test_query_cache_key_changes_when_database_changes(tmp_path: Path) -> None:
    database = tmp_path / "retail.duckdb"
    database.write_bytes(b"database")
    before = query_cache_key(database, "How many products?")
    database.write_bytes(b"new database contents")

    assert query_cache_key(database, "How many products?") != before


def test_schema_catalog_is_reused_for_unchanged_database(sample_database: Path) -> None:
    cache = {}

    first = load_schema_catalog(cache, sample_database, sample_limit=0)
    second = load_schema_catalog(cache, sample_database, sample_limit=0)

    assert first is second
    assert len(first.tables) > 0
