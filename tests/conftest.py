from pathlib import Path

import pytest

from queris.sample_data import create_sample_database

MALICIOUS_SQL_CASES = [
    pytest.param("INSERT INTO events VALUES (1)", id="insert"),
    pytest.param("UPDATE events SET value = 1", id="update"),
    pytest.param("DELETE FROM events", id="delete"),
    pytest.param("DROP TABLE events", id="drop"),
    pytest.param("ALTER TABLE events ADD COLUMN value INTEGER", id="alter"),
    pytest.param("CREATE TABLE events (value INTEGER)", id="create"),
    pytest.param("ATTACH 'other.duckdb' AS other", id="attach"),
    pytest.param("DETACH other", id="detach"),
    pytest.param("COPY events TO 'events.csv'", id="copy-to"),
    pytest.param("COPY events FROM 'events.csv'", id="copy-from"),
    pytest.param("PRAGMA version", id="pragma"),
    pytest.param("INSTALL httpfs", id="install-extension"),
    pytest.param("LOAD httpfs", id="load-extension"),
    pytest.param("SET threads = 4", id="set"),
    pytest.param("CALL checkpoint()", id="call"),
    pytest.param("SELECT * INTO copied_events FROM events", id="select-into"),
    pytest.param("SELECT 1; DROP TABLE events", id="stacked-statement"),
    pytest.param("/* harmless? */ DrOp/**/ TaBlE events", id="comments-and-casing"),
    pytest.param(
        "WITH source AS (SELECT 1) INSERT INTO events SELECT * FROM source",
        id="nested-insert",
    ),
    pytest.param("COPY (SELECT * FROM events) TO 'events.csv'", id="copy-query"),
    pytest.param("SELECT * FROM read_csv_auto('events.csv')", id="read-csv"),
    pytest.param("SELECT * FROM read_parquet('events.parquet')", id="read-parquet"),
    pytest.param("SELECT * FROM sqlite_scan('other.db', 'events')", id="sqlite-scan"),
    pytest.param("SELECT * FROM query('SELECT * FROM events')", id="dynamic-query"),
]


@pytest.fixture
def sample_database(tmp_path: Path) -> Path:
    return create_sample_database(tmp_path / "retail.duckdb")


@pytest.fixture(params=MALICIOUS_SQL_CASES)
def malicious_sql(request: pytest.FixtureRequest) -> str:
    """Return one hand-written SQL policy bypass attempt."""
    return request.param
