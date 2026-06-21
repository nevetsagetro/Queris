from pathlib import Path

import duckdb
import pytest

from queris.database import read_only_connection
from queris.sample_data import create_sample_database


@pytest.fixture
def sample_database(tmp_path: Path) -> Path:
    return create_sample_database(tmp_path / "retail.duckdb")


def test_create_sample_database_loads_expected_rows(sample_database: Path) -> None:
    with read_only_connection(sample_database) as connection:
        assert connection.execute("SELECT count(*) FROM orders").fetchone() == (4,)
        assert connection.execute("SELECT count(*) FROM order_items").fetchone() == (5,)


def test_create_sample_database_refuses_to_replace_existing_file(
    sample_database: Path,
) -> None:
    with pytest.raises(FileExistsError, match="Refusing to replace"):
        create_sample_database(sample_database)


def test_read_only_connection_rejects_writes(sample_database: Path) -> None:
    with (
        read_only_connection(sample_database) as connection,
        pytest.raises(duckdb.Error, match="read-only mode"),
    ):
        connection.execute("CREATE TABLE forbidden (value INTEGER)")


def test_read_only_connection_requires_existing_file(tmp_path: Path) -> None:
    with (
        pytest.raises(FileNotFoundError, match="does not exist"),
        read_only_connection(tmp_path / "missing.duckdb"),
    ):
        pass
