"""DuckDB connection boundaries used by the runtime."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb


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
