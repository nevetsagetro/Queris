"""Fast, deterministic execution path for the curated demo questions."""

from pathlib import Path
from time import perf_counter

from queris.adapters import DatabaseAdapter
from queris.agent_loop import AgentQueryResult
from queris.database import execute_read_only, read_only_connection
from queris.demo_registry import DemoDefinition, get_demo_definition
from queris.query_sources import extract_query_sources
from queris.schema import DatabaseSchema, introspect_schema


def demo_definition(example_id: str) -> DemoDefinition | None:
    """Resolve a demo through the typed registry."""
    return get_demo_definition(example_id)


def run_demo_query(database_path: str | Path, definition: DemoDefinition) -> AgentQueryResult:
    """Execute prepared read-only SQL without constructing or calling an LLM."""
    started_at = perf_counter()
    with read_only_connection(database_path) as connection:
        schema = introspect_schema(connection, sample_limit=0)
        sql = _prepared_sql(definition, schema)
        cursor = execute_read_only(connection, sql)
        columns = tuple(description[0] for description in cursor.description or ())
        rows = tuple(tuple(row) for row in cursor.fetchall())
    return AgentQueryResult(
        status="success",
        question=definition.example.question,
        sql=sql,
        columns=columns,
        rows=rows,
        sources=extract_query_sources(sql, schema),
        retry_count=0,
        latency_ms=(perf_counter() - started_at) * 1000,
    )


def run_prepared_query(database_path: str | Path, question: str, sql: str) -> AgentQueryResult:
    """Execute a server-selected read-only query for a generic dataset recommendation."""
    started_at = perf_counter()
    with read_only_connection(database_path) as connection:
        schema = introspect_schema(connection, sample_limit=0)
        cursor = execute_read_only(connection, sql)
        columns = tuple(description[0] for description in cursor.description or ())
        rows = tuple(tuple(row) for row in cursor.fetchall())
    return AgentQueryResult(
        status="success",
        question=question,
        sql=sql,
        columns=columns,
        rows=rows,
        sources=extract_query_sources(sql, schema),
        retry_count=0,
        latency_ms=(perf_counter() - started_at) * 1000,
    )


def run_adapter_query(adapter: DatabaseAdapter, question: str, sql: str) -> AgentQueryResult:
    """Execute a previously validated query through a live read-only adapter."""
    started_at = perf_counter()
    schema = adapter.introspect(sample_limit=0)
    result = adapter.execute(sql)
    return AgentQueryResult(
        status="success",
        question=question,
        sql=sql,
        columns=result.columns,
        rows=result.rows,
        sources=extract_query_sources(sql, schema),
        retry_count=0,
        latency_ms=(perf_counter() - started_at) * 1000,
    )


def _prepared_sql(definition: DemoDefinition, schema: DatabaseSchema) -> str:
    """Use the registered builder or a safe fallback for another schema fixture."""
    table_columns = {
        table.name: {column.name for column in table.columns} for table in schema.tables
    }
    required = {"orders": {"invoice_no", "country"}, "order_items": {"invoice_no", "revenue"}}
    if all(
        table in table_columns and columns <= table_columns[table]
        for table, columns in required.items()
    ):
        return definition.sql_builder(definition.variant).strip()
    table = "orders" if "orders" in table_columns else schema.tables[0].name
    escaped_table = table.replace('"', '""')
    return f'SELECT COUNT(*) AS row_count FROM "{escaped_table}"'
