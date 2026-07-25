"""Repeatable five-question Phase 8 live demo exit evaluation."""

import argparse
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from queris.agent_loop import (
    DEFAULT_MAX_RETRIES,
    CorrectingSQLGenerator,
    FailureStage,
    run_agent_loop,
)
from queris.demo_presenter import present_success
from queris.evaluation_metrics import matches_evaluation_result
from queris.evaluation_set import EvaluationSet, EvaluationSetCase, load_evaluation_set
from queris.generation import GeminiSQLGenerator
from queris.pipeline import FullSchemaSelector

DEMO_EXIT_TOTAL = 5


class DemoEvaluationOutcome(BaseModel):
    """Auditable result and explanation state for one live demo question."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    question: str
    status: Literal["success", "failure", "clarification", "no_answer", "error"]
    final_sql: str | None = None
    result_correct: bool
    explanation: str | None = None
    retry_count: int = Field(ge=0)
    latency_ms: float = Field(ge=0)
    blocked: bool
    passed: bool
    failure_stage: FailureStage | None = None
    error: str | None = None


class DemoEvaluationSummary(BaseModel):
    """Strict Phase 8 five-question exit state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    required: int = DEMO_EXIT_TOTAL
    passed: bool


class DemoEvaluationReport(BaseModel):
    """Local structured audit report for one demo exit run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    summary: DemoEvaluationSummary
    outcomes: tuple[DemoEvaluationOutcome, ...]


def run_demo_evaluation(
    database_path: str | Path,
    evaluation_set: EvaluationSet,
    generator: CorrectingSQLGenerator,
    *,
    sample_limit: int = 3,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> tuple[DemoEvaluationOutcome, ...]:
    """Run every reviewed demo question through the live safe agent."""
    return tuple(
        _run_demo_case(
            database_path,
            case,
            generator,
            sample_limit=sample_limit,
            max_retries=max_retries,
        )
        for case in evaluation_set.cases
    )


def summarize_demo_evaluation(
    outcomes: tuple[DemoEvaluationOutcome, ...],
) -> DemoEvaluationSummary:
    """Require all five reviewed demo questions to pass."""
    passed_cases = sum(outcome.passed for outcome in outcomes)
    return DemoEvaluationSummary(
        total=len(outcomes),
        passed_cases=passed_cases,
        passed=len(outcomes) == DEMO_EXIT_TOTAL and passed_cases == DEMO_EXIT_TOTAL,
    )


def write_demo_evaluation_report(
    path: str | Path,
    evaluation_set: EvaluationSet,
    outcomes: tuple[DemoEvaluationOutcome, ...],
) -> Path:
    """Replace one ignored local demo evaluation report."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = DemoEvaluationReport(
        dataset_id=evaluation_set.dataset_id,
        summary=summarize_demo_evaluation(outcomes),
        outcomes=outcomes,
    )
    output_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return output_path


def _run_demo_case(
    database_path: str | Path,
    case: EvaluationSetCase,
    generator: CorrectingSQLGenerator,
    *,
    sample_limit: int,
    max_retries: int,
) -> DemoEvaluationOutcome:
    try:
        result = run_agent_loop(
            database_path,
            case.question,
            generator,
            FullSchemaSelector(),
            sample_limit=sample_limit,
            max_retries=max_retries,
        )
    except Exception as error:
        return DemoEvaluationOutcome(
            case_id=case.id,
            question=case.question,
            status="error",
            result_correct=False,
            retry_count=0,
            latency_ms=0,
            blocked=False,
            passed=False,
            error=f"{type(error).__name__}: {error}",
        )

    result_correct = result.status == "success" and matches_evaluation_result(
        case,
        result.columns,
        result.rows,
    )
    explanation = present_success(result).explanation if result.status == "success" else None
    passed = result_correct and bool(explanation)
    return DemoEvaluationOutcome(
        case_id=case.id,
        question=case.question,
        status=result.status,
        final_sql=result.sql,
        result_correct=result_correct,
        explanation=explanation,
        retry_count=result.retry_count,
        latency_ms=result.latency_ms,
        blocked=result.blocked,
        passed=passed,
        failure_stage=result.failure_stage,
        error=result.error,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Queris Phase 8 live demo exit evaluation")
    parser.add_argument("database", type=Path, help="Existing retail .duckdb path")
    parser.add_argument(
        "--questions",
        type=Path,
        default=Path("evals/demo_v1.json"),
        help="Versioned five-question demo evaluation set",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/results/demo-exit.json"),
        help="Ignored local structured audit report",
    )
    parser.add_argument("--samples", type=int, default=3, help="Sample values per column")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Maximum correction retries per question",
    )
    args = parser.parse_args()

    evaluation_set = load_evaluation_set(args.questions)
    outcomes = run_demo_evaluation(
        args.database,
        evaluation_set,
        GeminiSQLGenerator(),
        sample_limit=args.samples,
        max_retries=args.max_retries,
    )
    summary = summarize_demo_evaluation(outcomes)
    output_path = write_demo_evaluation_report(args.output, evaluation_set, outcomes)
    print(summary.model_dump_json())
    print(output_path)
    if not summary.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
