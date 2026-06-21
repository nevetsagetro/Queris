import pytest
from sqlglot import exp

from queris.sql_validation import SQLValidationError, parse_read_only


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "WITH totals AS (SELECT 1 AS value) SELECT value FROM totals",
        "SELECT 1 UNION ALL SELECT 2",
        "/* leading comment */ SeLeCt 1 AS value",
        "WITH nested AS (SELECT 1 AS value) SELECT value FROM nested",
    ],
)
def test_parse_read_only_accepts_queries(sql: str) -> None:
    assert isinstance(parse_read_only(sql), exp.Query)


def test_parse_read_only_rejects_malicious_query_set(malicious_sql: str) -> None:
    with pytest.raises(SQLValidationError):
        parse_read_only(malicious_sql)


@pytest.mark.parametrize("sql", ["", "   "])
def test_parse_read_only_rejects_empty_input(sql: str) -> None:
    with pytest.raises(SQLValidationError, match="non-empty"):
        parse_read_only(sql)


def test_parse_read_only_rejects_multiple_statements() -> None:
    with pytest.raises(SQLValidationError, match="Exactly one"):
        parse_read_only("SELECT 1; SELECT 2")


def test_parse_read_only_hides_parser_details() -> None:
    with pytest.raises(SQLValidationError, match="could not be parsed"):
        parse_read_only("SELECT FROM")
