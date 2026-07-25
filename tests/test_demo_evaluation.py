import json
from pathlib import Path

from queris.demo_evaluation import (
    DEMO_EXIT_TOTAL,
    run_demo_evaluation,
    summarize_demo_evaluation,
    write_demo_evaluation_report,
)
from queris.evaluation_set import EvaluationSet, load_evaluation_set
from queris.generation import SQLCorrectionContext
from queris.schema import DatabaseSchema

DEMO_SET_PATH = Path("evals/demo_v1.json")


class ReferenceGenerator:
    def __init__(self, evaluation_set: EvaluationSet) -> None:
        self._case_by_question = {case.question: case for case in evaluation_set.cases}

    def generate_sql(
        self,
        schema: DatabaseSchema,
        question: str,
        correction: SQLCorrectionContext | None = None,
    ) -> str:
        return self._case_by_question[question].expected_sql


class WrongGenerator:
    def generate_sql(
        self,
        schema: DatabaseSchema,
        question: str,
        correction: SQLCorrectionContext | None = None,
    ) -> str:
        return "SELECT 1 AS wrong_result"


def test_demo_set_has_five_representative_categories() -> None:
    evaluation_set = load_evaluation_set(DEMO_SET_PATH)

    assert len(evaluation_set.cases) == DEMO_EXIT_TOTAL
    assert {case.category for case in evaluation_set.cases} == {
        "simple-aggregation",
        "multi-table-join",
        "time-filtering",
        "group-by-having",
        "nested-subquery",
    }


def test_reference_demo_run_passes_all_exit_cases(sample_database: Path) -> None:
    evaluation_set = load_evaluation_set(DEMO_SET_PATH)
    outcomes = run_demo_evaluation(
        sample_database,
        evaluation_set,
        ReferenceGenerator(evaluation_set),
        sample_limit=0,
    )
    summary = summarize_demo_evaluation(outcomes)

    assert summary.total == DEMO_EXIT_TOTAL
    assert summary.passed_cases == DEMO_EXIT_TOTAL
    assert summary.passed is True
    assert all(outcome.result_correct and outcome.explanation for outcome in outcomes)


def test_executable_wrong_results_fail_demo_exit(sample_database: Path) -> None:
    evaluation_set = load_evaluation_set(DEMO_SET_PATH)
    outcomes = run_demo_evaluation(
        sample_database,
        evaluation_set,
        WrongGenerator(),
        sample_limit=0,
    )

    assert not any(outcome.passed for outcome in outcomes)
    assert summarize_demo_evaluation(outcomes).passed is False


def test_incomplete_demo_set_cannot_pass(sample_database: Path) -> None:
    evaluation_set = load_evaluation_set(DEMO_SET_PATH)
    subset = evaluation_set.model_copy(update={"cases": evaluation_set.cases[:4]})
    outcomes = run_demo_evaluation(
        sample_database,
        subset,
        ReferenceGenerator(subset),
        sample_limit=0,
    )

    assert summarize_demo_evaluation(outcomes).passed is False


def test_demo_report_contains_results_and_explanations(
    sample_database: Path,
    tmp_path: Path,
) -> None:
    evaluation_set = load_evaluation_set(DEMO_SET_PATH)
    outcomes = run_demo_evaluation(
        sample_database,
        evaluation_set,
        ReferenceGenerator(evaluation_set),
        sample_limit=0,
    )

    output_path = write_demo_evaluation_report(
        tmp_path / "demo-exit.json",
        evaluation_set,
        outcomes,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["summary"]["passed"] is True
    assert len(payload["outcomes"]) == DEMO_EXIT_TOTAL
    assert payload["outcomes"][0]["explanation"] == "The result is 4 for order_count."
