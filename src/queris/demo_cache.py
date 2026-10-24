"""In-memory cache helpers for the Streamlit demo."""

from pathlib import Path

from queris.agent_loop import AgentQueryResult
from queris.database import read_only_connection
from queris.schema import DatabaseSchema, introspect_schema

QUERY_CACHE_VERSION = "v1"
SCHEMA_CACHE_VERSION = "v1"


def query_cache_key(database_path: Path, question: str) -> str:
    """Return a session-cache key invalidated by database file changes."""
    resolved_path = database_path.expanduser().resolve()
    stat = resolved_path.stat()
    normalized_question = " ".join(question.split()).casefold()
    return (
        f"{QUERY_CACHE_VERSION}:{resolved_path}:{stat.st_mtime_ns}:{stat.st_size}:"
        f"{normalized_question}"
    )


def cache_result(
    cache: dict[str, AgentQueryResult],
    database_path: Path,
    question: str,
    result: AgentQueryResult,
) -> None:
    """Store one terminal result in the caller-owned session cache."""
    cache[query_cache_key(database_path, question)] = result


def cached_result(
    cache: dict[str, AgentQueryResult],
    database_path: Path,
    question: str,
) -> AgentQueryResult | None:
    """Return a cached result, or ``None`` when the database/question changed."""
    return cache.get(query_cache_key(database_path, question))


def schema_cache_key(database_path: Path, sample_limit: int = 3) -> str:
    """Return a schema-cache key invalidated by DuckDB file changes."""
    resolved_path = database_path.expanduser().resolve()
    stat = resolved_path.stat()
    return (
        f"{SCHEMA_CACHE_VERSION}:{resolved_path}:{stat.st_mtime_ns}:{stat.st_size}:{sample_limit}"
    )


def load_schema_catalog(
    cache: dict[str, DatabaseSchema],
    database_path: Path,
    *,
    sample_limit: int = 3,
) -> DatabaseSchema:
    """Load a read-only schema catalog once per unchanged database file."""
    key = schema_cache_key(database_path, sample_limit)
    if key not in cache:
        with read_only_connection(database_path) as connection:
            cache[key] = introspect_schema(connection, sample_limit=sample_limit)
    return cache[key]
