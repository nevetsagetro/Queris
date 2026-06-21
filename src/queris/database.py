"""DuckDB connection boundaries used by the runtime."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol, Self, TypeVar

import duckdb

from queris.sql_validation import parse_read_only


class _ExecutableConnection(Protocol):
    def execute(self, query: str) -> Self: ...


ConnectionT = TypeVar("ConnectionT", bound=_ExecutableConnection)


@contextmanager
def read_only_connection(database_path: str | Path) -> Iterator[duckdb.DuckDBPyConnection]:
    """Open an existing DuckDB database in read-only mode and close it afterwards."""
    path = Path(database_path)
    if not path.is_file():
        raise FileNotFoundError(f"DuckDB database does not exist: {path}")

    connection = duckdb.connect(database=str(path), read_only=True)
    try:
        yield connection
    finally:
        connection.close()


def execute_read_only(
    connection: ConnectionT,
    sql: str,
) -> ConnectionT:
    """Validate one query before sending it to DuckDB for execution."""
    parse_read_only(sql)
    return connection.execute(sql)
