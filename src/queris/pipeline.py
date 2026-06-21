"""Linear baseline pipeline for safe text-to-SQL execution."""

from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from queris.database import execute_read_only, read_only_connection
from queris.schema import DatabaseSchema, introspect_schema
from queris.schema_retrieval import SchemaMatch


class SQLGenerator(Protocol):
    """Generate one SQL string from a schema and user question."""

    def generate_sql(self, schema: DatabaseSchema, question: str) -> str: ...


class SchemaSelector(Protocol):
    """Select the live schema context supplied to SQL generation."""

    def select_schema(self, schema: DatabaseSchema, question: str) -> DatabaseSchema: ...


class SchemaRetriever(Protocol):
    """Retrieve ranked schema matches for one question."""

    def retrieve(self, question: str) -> tuple[SchemaMatch, ...]: ...


class FullSchemaSelector:
    """Preserve the Phase 2 full-schema evaluation baseline explicitly."""

    def select_schema(self, schema: DatabaseSchema, question: str) -> DatabaseSchema:
        return schema


class RetrievedSchemaSelector:
    """Map ranked retrieval matches back to the current live schema."""

    def __init__(self, retriever: SchemaRetriever) -> None:
        self._retriever = retriever

    def select_schema(self, schema: DatabaseSchema, question: str) -> DatabaseSchema:
        return select_retrieved_schema(schema, self._retriever.retrieve(question))


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
    schema_selector: SchemaSelector,
    *,
    sample_limit: int = 3,
) -> QueryResult:
    """Generate, validate, and execute one query against a read-only database."""
    normalized_question = _normalize_question(question)

    with read_only_connection(database_path) as connection:
        full_schema = introspect_schema(connection, sample_limit=sample_limit)
        selected_schema = schema_selector.select_schema(full_schema, normalized_question)
        sql = generator.generate_sql(selected_schema, normalized_question)
        cursor = execute_read_only(connection, sql)
        columns = tuple(description[0] for description in cursor.description or ())
        rows = tuple(tuple(row) for row in cursor.fetchall())

    return QueryResult(
        question=normalized_question,
        sql=sql,
        columns=columns,
        rows=rows,
    )


def select_retrieved_schema(
    schema: DatabaseSchema,
    matches: tuple[SchemaMatch, ...],
) -> DatabaseSchema:
    """Build minimal live schema context from ranked table and column matches."""
    selected_columns: dict[tuple[str, str], set[str] | None] = {}
    for match in matches:
        reference = (match.schema_name, match.table_name)
        if match.kind == "table":
            selected_columns[reference] = None
        elif match.column_name is not None and selected_columns.get(reference, set()) is not None:
            existing = selected_columns.setdefault(reference, set())
            if existing is not None:
                existing.add(match.column_name)

    selected_tables = []
    for table in schema.tables:
        reference = (table.schema_name, table.name)
        if reference not in selected_columns:
            continue
        column_names = selected_columns[reference]
        if column_names is None:
            selected_tables.append(table)
            continue
        columns = tuple(column for column in table.columns if column.name in column_names)
        if columns:
            selected_tables.append(table.model_copy(update={"columns": columns}))

    if not selected_tables:
        raise ValueError("retrieval did not select any live schema objects")
    return DatabaseSchema(tables=tuple(selected_tables))


def _normalize_question(question: str) -> str:
    if not isinstance(question, str):
        raise TypeError("question must be a string")
    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("question must be a non-empty string")
    return normalized_question
