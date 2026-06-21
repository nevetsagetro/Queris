"""Repeatable evaluation for the Phase 2 text-to-SQL baseline."""

import argparse
import json
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from queris.generation import GeminiSQLGenerator
from queris.pipeline import FullSchemaSelector, QueryResult, SQLGenerator, run_text_to_sql
from queris.schema import DatabaseSchema

BASELINE_PASS_COUNT = 7
BASELINE_TOTAL_COUNT = 10


class EvaluationCase(BaseModel):
    """One versioned question and its expected result values."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    question: str = Field(min_length=1)
    expected_column_count: int = Field(gt=0)
    expected_rows: tuple[tuple[Any, ...], ...]


class EvaluationRecord(BaseModel):
    """Auditable outcome for one baseline question."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    question: str
    generated_sql: str | None
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    correct: bool
    error: str | None = None


class EvaluationSummary(BaseModel):
    """Aggregate baseline accuracy and pass status."""

    model_config = ConfigDict(frozen=True)

    total: int
    correct: int
    required: int
    passed: bool


class _RecordingGenerator:
    def __init__(self, delegate: SQLGenerator) -> None:
        self._delegate = delegate
        self.generated_sql: str | None = None

    def generate_sql(self, schema: DatabaseSchema, question: str) -> str:
        self.generated_sql = self._delegate.generate_sql(schema, question)
        return self.generated_sql


def load_evaluation_cases(path: str | Path) -> tuple[EvaluationCase, ...]:
    """Load and validate a JSON array of unique evaluation cases."""
    raw_cases = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = TypeAdapter(tuple[EvaluationCase, ...]).validate_python(raw_cases)
    case_ids = [case.id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("evaluation case ids must be unique")
    if not cases:
        raise ValueError("evaluation set must contain at least one case")
    return cases


def run_evaluation(
    database_path: str | Path,
    cases: tuple[EvaluationCase, ...],
    generator: SQLGenerator,
    *,
    sample_limit: int = 3,
) -> tuple[EvaluationRecord, ...]:
    """Run all cases independently so every outcome can be audited."""
    records = []
    for case in cases:
        recording_generator = _RecordingGenerator(generator)
        try:
            result = run_text_to_sql(
                database_path,
                case.question,
                recording_generator,
                FullSchemaSelector(),
                sample_limit=sample_limit,
            )
        except Exception as error:
            records.append(
                EvaluationRecord(
                    case_id=case.id,
                    question=case.question,
                    generated_sql=recording_generator.generated_sql,
                    correct=False,
                    error=f"{type(error).__name__}: {error}",
                )
            )
            continue

        records.append(_record_result(case, result))
    return tuple(records)


def summarize_evaluation(
    records: tuple[EvaluationRecord, ...],
    *,
    required: int = BASELINE_PASS_COUNT,
) -> EvaluationSummary:
    """Summarize accuracy against the Phase 2 pass threshold."""
    correct = sum(record.correct for record in records)
    return EvaluationSummary(
        total=len(records),
        correct=correct,
        required=required,
        passed=len(records) == BASELINE_TOTAL_COUNT and correct >= required,
    )


def write_evaluation_records(
    path: str | Path,
    records: tuple[EvaluationRecord, ...],
) -> Path:
    """Write local JSONL audit records, replacing an earlier run at the same path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [record.model_dump_json() for record in records]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def _record_result(case: EvaluationCase, result: QueryResult) -> EvaluationRecord:
    return EvaluationRecord(
        case_id=case.id,
        question=case.question,
        generated_sql=result.sql,
        columns=result.columns,
        rows=result.rows,
        correct=_matches_expected(case, result),
    )


def _matches_expected(case: EvaluationCase, result: QueryResult) -> bool:
    if len(result.columns) != case.expected_column_count:
        return False
    actual_rows = Counter(_normalize_row(row) for row in result.rows)
    expected_rows = Counter(_normalize_row(row) for row in case.expected_rows)
    return actual_rows == expected_rows


def _normalize_row(row: tuple[Any, ...]) -> tuple[tuple[str, Any], ...]:
    return tuple(_normalize_value(value) for value in row)


def _normalize_value(value: Any) -> tuple[str, Any]:
    if isinstance(value, bool) or value is None:
        return ("literal", value)
    if isinstance(value, (Decimal, int, float)):
        return ("number", Decimal(str(value)).normalize())
    if isinstance(value, (date, datetime)):
        return ("date", value.isoformat())
    return ("literal", value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Queris text-to-SQL baseline")
    parser.add_argument("database", type=Path, help="Existing retail .duckdb path")
    parser.add_argument(
        "--questions",
        type=Path,
        default=Path("evals/baseline_questions.json"),
        help="Versioned evaluation case JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/results/baseline.jsonl"),
        help="Ignored local JSONL audit output",
    )
    parser.add_argument("--samples", type=int, default=3, help="Sample values per column")
    args = parser.parse_args()

    cases = load_evaluation_cases(args.questions)
    generator = GeminiSQLGenerator()
    records = run_evaluation(
        args.database,
        cases,
        generator,
        sample_limit=args.samples,
    )
    output_path = write_evaluation_records(args.output, records)
    summary = summarize_evaluation(records)
    print(summary.model_dump_json())
    print(output_path)
    if not summary.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
