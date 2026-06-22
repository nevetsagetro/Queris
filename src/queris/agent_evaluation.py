"""Repeatable Phase 5 self-correction exit evaluation."""

import argparse
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from queris.agent_loop import (
    DEFAULT_MAX_RETRIES,
    AgentQueryResult,
    CorrectingSQLGenerator,
    FailureStage,
    run_agent_loop,
)
from queris.evaluation import EvaluationCase, matches_expected_result
from queris.generation import GeminiSQLGenerator, SQLCorrectionContext
from queris.pipeline import FullSchemaSelector, QueryResult
from queris.schema import DatabaseSchema

AGENT_EVAL_PASS_COUNT = 3
AGENT_EVAL_TOTAL_COUNT = 5


class AgentEvaluationCase(EvaluationCase):
    """One question with a deliberately failing initial SQL attempt."""

    initial_sql: str = Field(min_length=1)


class AgentEvaluationRecord(BaseModel):
    """Auditable outcome for one self-correction case."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    question: str
    initial_sql: str
    final_sql: str | None = None
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[object, ...], ...] = ()
    retry_count: int = Field(ge=0)
    recovered: bool
    correct: bool
    failure_stage: FailureStage | None = None
    retries_exhausted: bool = False
    error: str | None = None


class AgentEvaluationSummary(BaseModel):
    """Aggregate self-correction accuracy and exit status."""

    model_config = ConfigDict(frozen=True)

    total: int
    correct: int
    required: int
    passed: bool


class _InjectedFailureGenerator:
    def __init__(self, initial_sql: str, delegate: CorrectingSQLGenerator) -> None:
        self.initial_sql = initial_sql
        self.delegate = delegate

    def generate_sql(
        self,
        schema: DatabaseSchema,
        question: str,
        correction: SQLCorrectionContext | None = None,
    ) -> str:
        if correction is None:
            return self.initial_sql
        return self.delegate.generate_sql(schema, question, correction)


def load_agent_evaluation_cases(path: str | Path) -> tuple[AgentEvaluationCase, ...]:
    """Load and validate unique versioned agent-loop cases."""
    raw_cases = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = TypeAdapter(tuple[AgentEvaluationCase, ...]).validate_python(raw_cases)
    case_ids = [case.id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("agent evaluation case ids must be unique")
    if not cases:
        raise ValueError("agent evaluation set must contain at least one case")
    return cases


def run_agent_evaluation(
    database_path: str | Path,
    cases: tuple[AgentEvaluationCase, ...],
    generator: CorrectingSQLGenerator,
    *,
    sample_limit: int = 3,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> tuple[AgentEvaluationRecord, ...]:
    """Run every injected-failure case independently through the live graph."""
    records = []
    for case in cases:
        try:
            result = run_agent_loop(
                database_path,
                case.question,
                _InjectedFailureGenerator(case.initial_sql, generator),
                FullSchemaSelector(),
                sample_limit=sample_limit,
                max_retries=max_retries,
            )
        except Exception as error:
            records.append(
                AgentEvaluationRecord(
                    case_id=case.id,
                    question=case.question,
                    initial_sql=case.initial_sql,
                    retry_count=0,
                    recovered=False,
                    correct=False,
                    error=f"{type(error).__name__}: {error}",
                )
            )
            continue
        records.append(_record_agent_result(case, result))
    return tuple(records)


def summarize_agent_evaluation(
    records: tuple[AgentEvaluationRecord, ...],
    *,
    required: int = AGENT_EVAL_PASS_COUNT,
) -> AgentEvaluationSummary:
    """Summarize correctness against the Phase 5 majority threshold."""
    correct = sum(record.correct for record in records)
    return AgentEvaluationSummary(
        total=len(records),
        correct=correct,
        required=required,
        passed=len(records) == AGENT_EVAL_TOTAL_COUNT and correct >= required,
    )


def write_agent_evaluation_records(
    path: str | Path,
    records: tuple[AgentEvaluationRecord, ...],
) -> Path:
    """Replace one ignored local JSONL audit output."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(record.model_dump_json() for record in records) + "\n",
        encoding="utf-8",
    )
    return output_path


def _record_agent_result(
    case: AgentEvaluationCase,
    result: AgentQueryResult,
) -> AgentEvaluationRecord:
    recovered = result.status == "success" and result.retry_count > 0
    correct = recovered and matches_expected_result(
        case,
        QueryResult(
            question=result.question,
            sql=result.sql,
            columns=result.columns,
            rows=result.rows,
        ),
    )
    return AgentEvaluationRecord(
        case_id=case.id,
        question=case.question,
        initial_sql=case.initial_sql,
        final_sql=result.sql,
        columns=result.columns,
        rows=result.rows,
        retry_count=result.retry_count,
        recovered=recovered,
        correct=correct,
        failure_stage=result.failure_stage,
        retries_exhausted=result.retries_exhausted,
        error=result.error,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Queris agent-loop exit evaluation")
    parser.add_argument("database", type=Path, help="Existing retail .duckdb path")
    parser.add_argument(
        "--questions",
        type=Path,
        default=Path("evals/agent_loop_questions.json"),
        help="Versioned injected-failure case JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/results/agent_loop.jsonl"),
        help="Ignored local JSONL audit output",
    )
    parser.add_argument("--samples", type=int, default=3, help="Sample values per column")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Correction retries after the injected attempt",
    )
    args = parser.parse_args()

    records = run_agent_evaluation(
        args.database,
        load_agent_evaluation_cases(args.questions),
        GeminiSQLGenerator(),
        sample_limit=args.samples,
        max_retries=args.max_retries,
    )
    output_path = write_agent_evaluation_records(args.output, records)
    summary = summarize_agent_evaluation(records)
    print(summary.model_dump_json())
    print(output_path)
    if not summary.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
