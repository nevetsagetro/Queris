"""Deterministic SQL formatting for human-readable result presentation."""

import sqlglot
from sqlglot.errors import SqlglotError


def format_sql_for_display(sql: str, *, dialect: str = "duckdb") -> str:
    """Pretty-print SQL without changing the executable SQL stored by Queris.

    Formatting is deliberately best-effort. If SQLGlot cannot parse a provider-specific
    statement, the original SQL is returned so presentation never blocks a result.
    """
    if not sql.strip():
        return sql
    try:
        return sqlglot.parse_one(sql, read=dialect).sql(dialect=dialect, pretty=True)
    except (SqlglotError, ValueError):
        return sql
