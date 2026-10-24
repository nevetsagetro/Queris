from pathlib import Path

import duckdb
import pytest

from queris.catalog_profile import profile_database


def test_profile_database_rejects_excessive_table_count(tmp_path: Path) -> None:
    database = tmp_path / "wide.duckdb"
    connection = duckdb.connect(str(database))
    connection.execute("CREATE TABLE one (value INTEGER)")
    connection.close()

    with pytest.raises(ValueError, match="profile limits must be positive"):
        profile_database(str(database), max_tables=0)
