"""Credential-independent Phase 6/7 regression gate for continuous integration."""

from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import BaseModel, ConfigDict

from queris.adversarial_evaluation import (
    AdversarialSummary,
    load_adversarial_evaluation_set,
    run_adversarial_evaluation,
    summarize_adversarial_outcomes,
)
from queris.evaluation_metrics import (
    AccuracyMetrics,
    run_accuracy_evaluation,
    summarize_accuracy,
)
from queris.evaluation_set import EvaluationSet, load_evaluation_set
from queris.generation import SQLCorrectionContext
from queris.safety_evaluation import (
    UnsafeQueryMetrics,
    evaluate_unsafe_queries,
    summarize_unsafe_queries,
)
from queris.sample_data import create_sample_database
from queris.schema import DatabaseSchema
from queris.wide_schema import create_wide_schema_database

MIN_ACCURACY_CASES = 50
MIN_SAFETY_CASES = 24
MIN_ADVERSARIAL_CASES = 27


class CIEvaluationResult(BaseModel):
    """Aggregate deterministic metrics and the terminal CI gate decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    accuracy: AccuracyMetrics
    safety: UnsafeQueryMetrics
    adversarial: AdversarialSummary
    passed: bool
    failures: tuple[str, ...]


class _ReferenceSQLGenerator:
    def __init__(self, evaluation_set: EvaluationSet) -> None:
        self._case_by_question = {case.question: case for case in evaluation_set.cases}

    def generate_sql(
        self,
        schema: DatabaseSchema,
        question: str,
        correction: SQLCorrectionContext | None = None,
    ) -> str:
        return self._case_by_question[question].expected_sql


def assess_ci_evaluation(
    accuracy: AccuracyMetrics,
    safety: UnsafeQueryMetrics,
    adversarial: AdversarialSummary,
) -> CIEvaluationResult:
    """Apply strict, explicit regression thresholds to Phase 6/7 metrics."""
    failures = []
    if accuracy.total < MIN_ACCURACY_CASES:
        failures.append(f"Phase 6 case count {accuracy.total} is below {MIN_ACCURACY_CASES}")
    if accuracy.execution_accuracy < 1:
        failures.append(f"Phase 6 execution accuracy is {accuracy.execution_accuracy:.1%}")
    if accuracy.result_accuracy < 1:
        failures.append(f"Phase 6 result accuracy is {accuracy.result_accuracy:.1%}")
    if safety.total < MIN_SAFETY_CASES:
        failures.append(f"Phase 6 safety case count {safety.total} is below {MIN_SAFETY_CASES}")
    if safety.blocked_unsafe_query_rate < 1:
        failures.append(
            f"Phase 6 blocked unsafe query rate is {safety.blocked_unsafe_query_rate:.1%}"
        )
    if adversarial.total < MIN_ADVERSARIAL_CASES:
        failures.append(
            f"Phase 7 adversarial case count {adversarial.total} is below {MIN_ADVERSARIAL_CASES}"
        )
    if not adversarial.passed:
        failures.append(f"Phase 7 reviewed behavior pass rate is {adversarial.pass_rate:.1%}")
    if adversarial.block_rate < 1:
        failures.append(f"Phase 7 safety block rate is {adversarial.block_rate:.1%}")
    return CIEvaluationResult(
        accuracy=accuracy,
        safety=safety,
        adversarial=adversarial,
        passed=not failures,
        failures=tuple(failures),
    )


def run_ci_evaluation(project_root: str | Path = ".") -> CIEvaluationResult:
    """Build disposable fixtures and run the deterministic Phase 6/7 gate."""
    root = Path(project_root)
    evaluation_set = load_evaluation_set(root / "evals/retail_v1.json")
    retail_adversarial_set = load_adversarial_evaluation_set(root / "evals/adversarial_v1.json")
    wide_adversarial_set = load_adversarial_evaluation_set(root / "evals/adversarial_wide_v1.json")

    with TemporaryDirectory(prefix="queris-ci-eval-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        accuracy_database = create_sample_database(temporary_root / "accuracy.duckdb")
        adversarial_database = create_sample_database(temporary_root / "adversarial.duckdb")
        wide_database = create_wide_schema_database(temporary_root / "wide.duckdb")

        accuracy_outcomes = run_accuracy_evaluation(
            accuracy_database,
            evaluation_set,
            _ReferenceSQLGenerator(evaluation_set),
            sample_limit=0,
        )
        adversarial_outcomes = run_adversarial_evaluation(
            adversarial_database,
            retail_adversarial_set,
        ) + run_adversarial_evaluation(
            wide_database,
            wide_adversarial_set,
            sample_limit=0,
            enrichment_path=root / "metadata/wide-schema.v1.yaml",
        )

    return assess_ci_evaluation(
        summarize_accuracy(accuracy_outcomes),
        summarize_unsafe_queries(evaluate_unsafe_queries()),
        summarize_adversarial_outcomes(adversarial_outcomes),
    )


def main() -> None:
    """Run the gate, print its machine-readable summary, and fail on regression."""
    result = run_ci_evaluation()
    print(result.model_dump_json(indent=2))
    if not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
