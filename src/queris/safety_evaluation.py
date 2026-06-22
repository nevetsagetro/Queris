"""Auditable blocked-unsafe-query evaluation over reviewed SQL attacks."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from queris.sql_validation import SQLValidationError, parse_read_only

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class UnsafeQueryCase(BaseModel):
    """One reviewed SQL policy bypass attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    sql: NonEmptyString


class UnsafeQueryOutcome(BaseModel):
    """Auditable validation outcome for one unsafe SQL case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    sql: str
    blocked: bool
    error: str | None = None

    @model_validator(mode="after")
    def require_block_diagnostic(self) -> Self:
        if self.blocked != (self.error is not None):
            raise ValueError("blocked outcome must contain exactly one validation diagnostic")
        return self


class UnsafeQueryMetrics(BaseModel):
    """Aggregate blocked-unsafe-query rate over all reviewed attempts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total: int = Field(ge=0)
    blocked: int = Field(ge=0)
    blocked_unsafe_query_rate: float = Field(ge=0, le=1)


UNSAFE_QUERY_CASES = tuple(
    UnsafeQueryCase(id=case_id, sql=sql)
    for case_id, sql in (
        ("insert", "INSERT INTO events VALUES (1)"),
        ("update", "UPDATE events SET value = 1"),
        ("delete", "DELETE FROM events"),
        ("drop", "DROP TABLE events"),
        ("alter", "ALTER TABLE events ADD COLUMN value INTEGER"),
        ("create", "CREATE TABLE events (value INTEGER)"),
        ("attach", "ATTACH 'other.duckdb' AS other"),
        ("detach", "DETACH other"),
        ("copy-to", "COPY events TO 'events.csv'"),
        ("copy-from", "COPY events FROM 'events.csv'"),
        ("pragma", "PRAGMA version"),
        ("install-extension", "INSTALL httpfs"),
        ("load-extension", "LOAD httpfs"),
        ("set", "SET threads = 4"),
        ("call", "CALL checkpoint()"),
        ("select-into", "SELECT * INTO copied_events FROM events"),
        ("stacked-statement", "SELECT 1; DROP TABLE events"),
        ("comments-and-casing", "/* harmless? */ DrOp/**/ TaBlE events"),
        ("nested-insert", "WITH source AS (SELECT 1) INSERT INTO events SELECT * FROM source"),
        ("copy-query", "COPY (SELECT * FROM events) TO 'events.csv'"),
        ("read-csv", "SELECT * FROM read_csv_auto('events.csv')"),
        ("read-parquet", "SELECT * FROM read_parquet('events.parquet')"),
        ("sqlite-scan", "SELECT * FROM sqlite_scan('other.db', 'events')"),
        ("dynamic-query", "SELECT * FROM query('SELECT * FROM events')"),
    )
)


def evaluate_unsafe_queries(
    cases: tuple[UnsafeQueryCase, ...] = UNSAFE_QUERY_CASES,
) -> tuple[UnsafeQueryOutcome, ...]:
    """Validate reviewed attacks without opening or executing against a database."""
    outcomes = []
    for case in cases:
        try:
            parse_read_only(case.sql)
        except SQLValidationError as error:
            outcomes.append(
                UnsafeQueryOutcome(
                    case_id=case.id,
                    sql=case.sql,
                    blocked=True,
                    error=str(error),
                )
            )
        else:
            outcomes.append(
                UnsafeQueryOutcome(
                    case_id=case.id,
                    sql=case.sql,
                    blocked=False,
                )
            )
    return tuple(outcomes)


def summarize_unsafe_queries(
    outcomes: tuple[UnsafeQueryOutcome, ...],
) -> UnsafeQueryMetrics:
    """Calculate the blocked rate over all attempted unsafe queries."""
    total = len(outcomes)
    blocked = sum(outcome.blocked for outcome in outcomes)
    return UnsafeQueryMetrics(
        total=total,
        blocked=blocked,
        blocked_unsafe_query_rate=blocked / total if total else 0,
    )
