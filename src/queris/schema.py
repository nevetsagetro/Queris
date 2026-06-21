"""Structured DuckDB schema introspection."""

import argparse
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from queris.database import read_only_connection

MAX_SAMPLE_VALUES = 10


class ColumnSchema(BaseModel):
    """Metadata and untrusted sample values for one database column."""

    model_config = ConfigDict(frozen=True)

    name: str
    data_type: str
    nullable: bool
    ordinal_position: int
    sample_values: tuple[Any, ...] = Field(default_factory=tuple)


class TableSchema(BaseModel):
    """Metadata for one base table."""

    model_config = ConfigDict(frozen=True)

    schema_name: str
    name: str
    columns: tuple[ColumnSchema, ...]


class DatabaseSchema(BaseModel):
    """Serializable description of the base tables visible to DuckDB."""

    model_config = ConfigDict(frozen=True)

    tables: tuple[TableSchema, ...]


def introspect_schema(
    connection: duckdb.DuckDBPyConnection,
    *,
    sample_limit: int = 3,
) -> DatabaseSchema:
    """Describe base tables and collect a bounded set of untrusted sample values."""
    if not 0 <= sample_limit <= MAX_SAMPLE_VALUES:
        raise ValueError(f"sample_limit must be between 0 and {MAX_SAMPLE_VALUES}")

    table_rows = connection.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY table_schema, table_name
        """
    ).fetchall()

    tables = tuple(
        _introspect_table(connection, schema_name, table_name, sample_limit)
        for schema_name, table_name in table_rows
    )
    return DatabaseSchema(tables=tables)


def _introspect_table(
    connection: duckdb.DuckDBPyConnection,
    schema_name: str,
    table_name: str,
    sample_limit: int,
) -> TableSchema:
    column_rows = connection.execute(
        """
        SELECT column_name, data_type, is_nullable = 'YES', ordinal_position
        FROM information_schema.columns
        WHERE table_schema = ? AND table_name = ?
        ORDER BY ordinal_position
        """,
        [schema_name, table_name],
    ).fetchall()

    columns = tuple(
        ColumnSchema(
            name=column_name,
            data_type=data_type,
            nullable=nullable,
            ordinal_position=ordinal_position,
            sample_values=_sample_values(
                connection,
                schema_name,
                table_name,
                column_name,
                sample_limit,
            ),
        )
        for column_name, data_type, nullable, ordinal_position in column_rows
    )
    return TableSchema(schema_name=schema_name, name=table_name, columns=columns)


def _sample_values(
    connection: duckdb.DuckDBPyConnection,
    schema_name: str,
    table_name: str,
    column_name: str,
    sample_limit: int,
) -> tuple[Any, ...]:
    if sample_limit == 0:
        return ()

    qualified_table = f"{_quote_identifier(schema_name)}.{_quote_identifier(table_name)}"
    column = _quote_identifier(column_name)
    rows = connection.execute(
        f"SELECT DISTINCT {column} FROM {qualified_table} WHERE {column} IS NOT NULL LIMIT ?",
        [sample_limit],
    ).fetchall()
    return tuple(row[0] for row in rows)


def _quote_identifier(identifier: str) -> str:
    escaped_identifier = identifier.replace('"', '""')
    return f'"{escaped_identifier}"'


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a DuckDB schema as JSON")
    parser.add_argument("database", type=Path, help="Existing .duckdb path")
    parser.add_argument(
        "--samples",
        type=int,
        default=3,
        help=f"Distinct values per column (0-{MAX_SAMPLE_VALUES})",
    )
    args = parser.parse_args()

    with read_only_connection(args.database) as connection:
        schema = introspect_schema(connection, sample_limit=args.samples)
    print(schema.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
