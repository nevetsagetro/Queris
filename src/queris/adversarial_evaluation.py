"""Versioned Phase 7 adversarial safety evaluation."""

import argparse
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from queris.agent_loop import FailureStage, run_agent_loop
from queris.generation import SQLCorrectionContext
from queris.pipeline import FullSchemaSelector
from queris.schema import DatabaseSchema

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DestructiveIntentCase(BaseModel):
    """One destructive question and worst-case generated SQL attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    category: Literal["destructive-intent"]
    question: NonEmptyString
    attempted_sql: NonEmptyString
    expected_outcome: Literal["blocked-before-execution"]


class AdversarialEvaluationSet(BaseModel):
    """One versioned collection of reviewed Phase 7 cases."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal[1]
    dataset_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    cases: tuple[DestructiveIntentCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_case_ids(self) -> Self:
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("adversarial case ids must be unique")
        return self


class AdversarialOutcome(BaseModel):
    """Auditable result for one destructive-intent attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    question: str
    attempted_sql: str
    final_sql: str
    blocked_before_execution: bool
    passed: bool
    failure_stage: FailureStage | None = None
    error: str | None = None


class AdversarialSummary(BaseModel):
    """Aggregate Phase 7 pass state with a strict block threshold."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    block_rate: float = Field(ge=0, le=1)
    passed: bool


class AdversarialEvaluationReport(BaseModel):
    """Versioned local audit report for one adversarial run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal[1] = 1
    dataset_id: str
    summary: AdversarialSummary
    outcomes: tuple[AdversarialOutcome, ...]


class _AttemptedSQLGenerator:
    def __init__(self, sql: str) -> None:
        self._sql = sql

    def generate_sql(
        self,
        schema: DatabaseSchema,
        question: str,
        correction: SQLCorrectionContext | None = None,
    ) -> str:
        return self._sql


def load_adversarial_evaluation_set(path: str | Path) -> AdversarialEvaluationSet:
    """Load and validate one versioned Phase 7 evaluation set."""
    return AdversarialEvaluationSet.model_validate_json(Path(path).read_text(encoding="utf-8"))


def run_destructive_intent_evaluation(
    database_path: str | Path,
    evaluation_set: AdversarialEvaluationSet,
    *,
    sample_limit: int = 0,
) -> tuple[AdversarialOutcome, ...]:
    """Inject every attempted SQL string through the real validation graph."""
    outcomes = []
    for case in evaluation_set.cases:
        result = run_agent_loop(
            database_path,
            case.question,
            _AttemptedSQLGenerator(case.attempted_sql),
            FullSchemaSelector(),
            sample_limit=sample_limit,
            max_retries=0,
        )
        blocked = result.status == "failure" and result.failure_stage == "validation"
        outcomes.append(
            AdversarialOutcome(
                case_id=case.id,
                question=case.question,
                attempted_sql=case.attempted_sql,
                final_sql=result.sql,
                blocked_before_execution=blocked,
                passed=blocked and case.expected_outcome == "blocked-before-execution",
                failure_stage=result.failure_stage,
                error=result.error,
            )
        )
    return tuple(outcomes)


def summarize_adversarial_outcomes(
    outcomes: tuple[AdversarialOutcome, ...],
) -> AdversarialSummary:
    """Require every reviewed destructive attempt to be blocked."""
    total = len(outcomes)
    passed_cases = sum(outcome.passed for outcome in outcomes)
    return AdversarialSummary(
        total=total,
        passed_cases=passed_cases,
        block_rate=passed_cases / total if total else 0,
        passed=total > 0 and passed_cases == total,
    )


def write_adversarial_report(
    path: str | Path,
    evaluation_set: AdversarialEvaluationSet,
    outcomes: tuple[AdversarialOutcome, ...],
) -> Path:
    """Replace one ignored local adversarial audit report."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = AdversarialEvaluationReport(
        dataset_id=evaluation_set.dataset_id,
        summary=summarize_adversarial_outcomes(outcomes),
        outcomes=outcomes,
    )
    output_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Queris Phase 7 adversarial evaluation")
    parser.add_argument("database", type=Path, help="Existing retail .duckdb path")
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/adversarial_v1.json"),
        help="Versioned Phase 7 adversarial case JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/results/adversarial.json"),
        help="Ignored local structured JSON report",
    )
    args = parser.parse_args()

    evaluation_set = load_adversarial_evaluation_set(args.cases)
    outcomes = run_destructive_intent_evaluation(args.database, evaluation_set)
    summary = summarize_adversarial_outcomes(outcomes)
    output_path = write_adversarial_report(args.output, evaluation_set, outcomes)
    print(summary.model_dump_json())
    print(output_path)
    if not summary.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
