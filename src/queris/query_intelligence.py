"""Persisted, read-only query intelligence generated from a discovered schema."""

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from queris.chart_recommender import ChartRecommendation, recommend_chart
from queris.database import execute_read_only, read_only_connection
from queris.dataset_demos import get_dataset_demos
from queris.schema import introspect_schema
from queris.workspace_discovery import schema_fingerprint


class ValidatedQuery(BaseModel):
    """One starter that executed successfully against the current snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    question: str
    reason: str
    tables: tuple[str, ...]
    sql: str
    chart: Literal["bar", "line", "metric", "table"]
    chart_recommendation: ChartRecommendation | None
    result_columns: tuple[str, ...]
    result_row_count: int = Field(ge=0)
    preview_rows: tuple[tuple[object, ...], ...] = ()
    validated: Literal[True] = True


class QueryIntelligenceReport(BaseModel):
    """Summary of the validated intelligence artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_query_count: int = Field(ge=0)
    validated_query_count: int = Field(ge=0)
    failed_query_ids: tuple[str, ...] = ()
    output_path: str


def generate_query_intelligence(
    database: str | Path,
    *,
    output: str | Path,
    target: int = 50,
) -> QueryIntelligenceReport:
    """Execute and persist the first validated starters for a local snapshot."""
    database_path = Path(database)
    output_path = Path(output)
    with read_only_connection(database_path) as connection:
        schema = introspect_schema(connection, sample_limit=0)
        fingerprint = schema_fingerprint(schema)
        demos = get_dataset_demos(schema)[:target]
        validated: list[ValidatedQuery] = []
        failures: list[str] = []
        for demo in demos:
            try:
                cursor = execute_read_only(connection, demo.sql)
                columns = tuple(description[0] for description in cursor.description or ())
                rows = tuple(tuple(row) for row in cursor.fetchall())
                validated.append(
                    ValidatedQuery(
                        id=demo.id,
                        schema_fingerprint=fingerprint,
                        question=demo.question,
                        reason=demo.reason,
                        tables=demo.tables,
                        sql=demo.sql,
                        chart=demo.chart,
                        chart_recommendation=recommend_chart(columns, rows),
                        result_columns=columns,
                        result_row_count=len(rows),
                        preview_rows=rows[:100],
                    )
                )
            except Exception:
                failures.append(demo.id)
    if not failures and len(validated) < min(target, 50):
        raise ValueError(
            f"snapshot produced only {len(validated)} validated starters; "
            f"at least {min(target, 50)} are required"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([item.model_dump(mode="json") for item in validated], indent=2) + "\n",
        encoding="utf-8",
    )
    return QueryIntelligenceReport(
        dataset_id=database_path.name,
        schema_fingerprint=fingerprint,
        generated_query_count=len(demos),
        validated_query_count=len(validated),
        failed_query_ids=tuple(failures),
        output_path=str(output_path),
    )


def selectively_refresh_query_intelligence(
    database: str | Path,
    *,
    output: str | Path,
    previous: str | Path,
    affected_tables: set[str],
    target: int = 50,
) -> QueryIntelligenceReport:
    """Refresh only starters whose referenced tables changed.

    Existing validated starters outside ``affected_tables`` are retained and
    rebound to the current schema fingerprint. This is deterministic local
    work; no LLM is involved in the refresh.
    """
    database_path = Path(database)
    output_path = Path(output)
    previous_items = [ValidatedQuery.model_validate(item) for item in json.loads(Path(previous).read_text(encoding="utf-8"))]
    previous_by_id = {item.id: item for item in previous_items}
    with read_only_connection(database_path) as connection:
        schema = introspect_schema(connection, sample_limit=0)
        fingerprint = schema_fingerprint(schema)
        demos = get_dataset_demos(schema)[:target]
        validated: list[ValidatedQuery] = []
        failures: list[str] = []
        for demo in demos:
            old = previous_by_id.get(demo.id)
            if old is not None and not affected_tables.intersection(demo.tables):
                validated.append(old.model_copy(update={"schema_fingerprint": fingerprint}))
                continue
            try:
                cursor = execute_read_only(connection, demo.sql)
                columns = tuple(description[0] for description in cursor.description or ())
                rows = tuple(tuple(row) for row in cursor.fetchall())
                validated.append(
                    ValidatedQuery(
                        id=demo.id,
                        schema_fingerprint=fingerprint,
                        question=demo.question,
                        reason=demo.reason,
                        tables=demo.tables,
                        sql=demo.sql,
                        chart=demo.chart,
                        chart_recommendation=recommend_chart(columns, rows),
                        result_columns=columns,
                        result_row_count=len(rows),
                        preview_rows=rows[:100],
                    )
                )
            except Exception:
                failures.append(demo.id)
    if not failures and len(validated) < min(target, 50):
        raise ValueError(
            f"snapshot produced only {len(validated)} validated starters; "
            f"at least {min(target, 50)} are required"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([item.model_dump(mode="json") for item in validated], indent=2) + "\n",
        encoding="utf-8",
    )
    return QueryIntelligenceReport(
        dataset_id=database_path.name,
        schema_fingerprint=fingerprint,
        generated_query_count=len(demos),
        validated_query_count=len(validated),
        failed_query_ids=tuple(failures),
        output_path=str(output_path),
    )


def main() -> None:
    """Generate a persisted intelligence artifact from one DuckDB snapshot."""
    parser = argparse.ArgumentParser(description="Generate validated Queris query intelligence")
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--target", type=int, default=50)
    args = parser.parse_args()
    output = args.output or Path("intelligence") / f"{args.database.stem}.queries.json"
    print(
        generate_query_intelligence(
            args.database, output=output, target=args.target
        ).model_dump_json(indent=2)
    )


if __name__ == "__main__":
    main()
