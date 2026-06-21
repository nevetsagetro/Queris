"""Linear baseline pipeline for safe text-to-SQL execution."""

from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from queris.database import execute_read_only, read_only_connection
from queris.schema import DatabaseSchema, introspect_schema


class SQLGenerator(Protocol):
    """Generate one SQL string from a schema and user question."""

    def generate_sql(self, schema: DatabaseSchema, question: str) -> str: ...


class QueryResult(BaseModel):
    """Structured result of one generated and validated analytics query."""

    model_config = ConfigDict(frozen=True)

    question: str
    sql: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


def run_text_to_sql(
    database_path: str | Path,
    question: str,
    generator: SQLGenerator,
    *,
    sample_limit: int = 3,
) -> QueryResult:
    """Generate, validate, and execute one query against a read-only database."""
    normalized_question = _normalize_question(question)

    with read_only_connection(database_path) as connection:
        schema = introspect_schema(connection, sample_limit=sample_limit)
        sql = generator.generate_sql(schema, normalized_question)
        cursor = execute_read_only(connection, sql)
        columns = tuple(description[0] for description in cursor.description or ())
        rows = tuple(tuple(row) for row in cursor.fetchall())

    return QueryResult(
        question=normalized_question,
        sql=sql,
        columns=columns,
        rows=rows,
    )


def _normalize_question(question: str) -> str:
    if not isinstance(question, str):
        raise TypeError("question must be a string")
    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("question must be a non-empty string")
    return normalized_question
