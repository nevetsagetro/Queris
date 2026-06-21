import pytest
from sqlglot import exp

from queris.sql_validation import SQLValidationError, parse_read_only


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "WITH totals AS (SELECT 1 AS value) SELECT value FROM totals",
        "SELECT 1 UNION ALL SELECT 2",
    ],
)
def test_parse_read_only_accepts_queries(sql: str) -> None:
    assert isinstance(parse_read_only(sql), exp.Query)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO events VALUES (1)",
        "UPDATE events SET value = 1",
        "DELETE FROM events",
        "DROP TABLE events",
        "ALTER TABLE events ADD COLUMN value INTEGER",
        "CREATE TABLE events (value INTEGER)",
        "ATTACH 'other.duckdb' AS other",
        "COPY events TO 'events.csv'",
        "PRAGMA version",
    ],
)
def test_parse_read_only_rejects_non_query_statements(sql: str) -> None:
    with pytest.raises(SQLValidationError, match="Only read-only"):
        parse_read_only(sql)


@pytest.mark.parametrize("sql", ["", "   "])
def test_parse_read_only_rejects_empty_input(sql: str) -> None:
    with pytest.raises(SQLValidationError, match="non-empty"):
        parse_read_only(sql)


def test_parse_read_only_rejects_multiple_statements() -> None:
    with pytest.raises(SQLValidationError, match="Exactly one"):
        parse_read_only("SELECT 1; SELECT 2")


def test_parse_read_only_rejects_select_into() -> None:
    with pytest.raises(SQLValidationError, match="SELECT INTO"):
        parse_read_only("SELECT * INTO copied_events FROM events")


def test_parse_read_only_hides_parser_details() -> None:
    with pytest.raises(SQLValidationError, match="could not be parsed"):
        parse_read_only("SELECT FROM")
