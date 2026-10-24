"""Database adapter boundary shared by local snapshots and optional live engines."""

from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from queris.database import execute_read_only, read_only_connection
from queris.schema import DatabaseSchema, introspect_schema
from queris.sql_validation import parse_read_only


class AdapterResult(BaseModel):
    """Bounded tabular output returned by an adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


class AdapterHealth(BaseModel):
    """Safe health result without connection details or credentials."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    engine: str
    available: bool
    error: str | None = None


class DatabaseAdapter(Protocol):
    """Minimal contract for discovery and safe query execution."""

    engine: str

    def healthcheck(self) -> AdapterHealth: ...

    def introspect(self, *, sample_limit: int = 3) -> DatabaseSchema: ...

    def execute(self, sql: str) -> AdapterResult: ...


@dataclass(frozen=True)
class DuckDBAdapter:
    """Read-only adapter for a local DuckDB snapshot."""

    database_path: str
    engine: str = "duckdb"

    def healthcheck(self) -> AdapterHealth:
        try:
            with read_only_connection(self.database_path):
                return AdapterHealth(engine=self.engine, available=True)
        except (OSError, RuntimeError) as error:
            return AdapterHealth(engine=self.engine, available=False, error=type(error).__name__)

    def introspect(self, *, sample_limit: int = 3) -> DatabaseSchema:
        with read_only_connection(self.database_path) as connection:
            return introspect_schema(connection, sample_limit=sample_limit)

    def execute(self, sql: str) -> AdapterResult:
        with read_only_connection(self.database_path) as connection:
            return _execute_cursor(execute_read_only(connection, sql))


class PostgresAdapter:
    """Optional live PostgreSQL adapter with an enforced read-only session."""

    engine = "postgresql"

    def __init__(
        self,
        dsn: str,
        *,
        connect_factory: Callable[[str], Any] | None = None,
        statement_timeout_ms: int = 30_000,
    ):
        if not dsn.strip():
            raise ValueError("dsn must be non-empty")
        if statement_timeout_ms <= 0:
            raise ValueError("statement_timeout_ms must be positive")
        self._dsn = dsn
        self._connect_factory = connect_factory or _postgres_connect
        self._statement_timeout_ms = statement_timeout_ms

    def healthcheck(self) -> AdapterHealth:
        try:
            with closing(self._connect()) as connection, closing(connection.cursor()) as cursor:
                cursor.execute("SELECT 1")
            return AdapterHealth(engine=self.engine, available=True)
        except Exception as error:
            return AdapterHealth(engine=self.engine, available=False, error=type(error).__name__)

    def introspect(self, *, sample_limit: int = 3) -> DatabaseSchema:
        if sample_limit < 0:
            raise ValueError("sample_limit must be non-negative")
        query = """
        SELECT table_schema, table_name, column_name, data_type,
               is_nullable = 'YES', ordinal_position
        FROM information_schema.columns
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY table_schema, table_name, ordinal_position
        """
        with closing(self._connect()) as connection:
            self._prepare_session(connection)
            with closing(connection.cursor()) as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
        return _postgres_schema(rows)

    def execute(self, sql: str) -> AdapterResult:
        parse_read_only(sql)
        with closing(self._connect()) as connection:
            self._prepare_session(connection)
            with closing(connection.cursor()) as cursor:
                cursor.execute(sql)
                return _execute_cursor(cursor)

    def _connect(self) -> Any:
        return self._connect_factory(self._dsn)

    def _prepare_session(self, connection: Any) -> None:
        with closing(connection.cursor()) as cursor:
            cursor.execute("SET default_transaction_read_only = on")
            cursor.execute(f"SET statement_timeout = {self._statement_timeout_ms}")


def _postgres_connect(dsn: str) -> Any:
    try:
        import psycopg
    except ImportError as error:
        raise RuntimeError("install the postgres extra to use PostgresAdapter") from error
    return psycopg.connect(dsn, autocommit=True)


def _execute_cursor(cursor: Any) -> AdapterResult:
    columns = tuple(description[0] for description in cursor.description or ())
    return AdapterResult(columns=columns, rows=tuple(tuple(row) for row in cursor.fetchall()))


def _postgres_schema(rows: list[tuple[Any, ...]]) -> DatabaseSchema:
    from queris.schema import ColumnSchema, TableSchema

    tables: dict[tuple[str, str], list[ColumnSchema]] = {}
    for schema_name, table_name, column_name, data_type, nullable, ordinal in rows:
        tables.setdefault((schema_name, table_name), []).append(
            ColumnSchema(
                name=column_name,
                data_type=data_type,
                nullable=nullable,
                ordinal_position=ordinal,
            )
        )
    return DatabaseSchema(
        tables=tuple(
            TableSchema(schema_name=schema_name, name=table_name, columns=tuple(columns))
            for (schema_name, table_name), columns in sorted(tables.items())
        )
    )
