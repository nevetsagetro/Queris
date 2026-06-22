from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from queris.evaluation_history import (
    compare_evaluation_reports,
    format_comparison_table,
    load_latest_compatible_report,
    write_historical_report,
)
from queris.evaluation_report import EvaluationReport


def _report(report, *, minutes: int = 0, **accuracy_updates) -> EvaluationReport:
    accuracy = report.accuracy.model_copy(update=accuracy_updates)
    return report.model_copy(
        update={
            "generated_at": report.generated_at + timedelta(minutes=minutes),
            "accuracy": accuracy,
        }
    )


def test_history_appends_reports_and_loads_latest_compatible(
    tmp_path: Path,
    phase6_report: EvaluationReport,
) -> None:
    first = _report(phase6_report, minutes=1)
    second = _report(phase6_report, minutes=2)
    current = _report(phase6_report, minutes=3)

    first_path = write_historical_report(tmp_path, first)
    second_path = write_historical_report(tmp_path, second)

    assert first_path != second_path
    assert load_latest_compatible_report(tmp_path, current) == second


def test_history_ignores_incompatible_case_sets(
    tmp_path: Path,
    phase6_report: EvaluationReport,
) -> None:
    incompatible = phase6_report.model_copy(update={"outcomes": phase6_report.outcomes[:1]})
    write_historical_report(tmp_path, incompatible)

    assert load_latest_compatible_report(tmp_path, _report(phase6_report, minutes=1)) is None


def test_comparison_marks_directional_regressions(phase6_report: EvaluationReport) -> None:
    previous = _report(
        phase6_report,
        execution_accuracy=1.0,
        result_accuracy=0.9,
        average_retry_count=1.0,
        total_tokens=100,
    )
    current = _report(
        phase6_report,
        minutes=1,
        execution_accuracy=0.8,
        result_accuracy=1.0,
        average_retry_count=2.0,
        total_tokens=90,
    )

    comparison = compare_evaluation_reports(previous, current)
    metrics = {metric.metric: metric for metric in comparison.metrics}

    assert metrics["Execution accuracy"].regressed is True
    assert metrics["Result accuracy"].regressed is False
    assert metrics["Average retries"].regressed is True
    assert metrics["Total tokens"].regressed is False
    assert comparison.has_regressions is True
    assert "REGRESSION" in format_comparison_table(comparison)


def test_comparison_rejects_incompatible_reports(phase6_report: EvaluationReport) -> None:
    incompatible = phase6_report.model_copy(update={"dataset_id": "other-v1"})

    with pytest.raises(ValueError, match="incompatible"):
        compare_evaluation_reports(phase6_report, incompatible)


@pytest.fixture
def phase6_report(sample_database: Path) -> EvaluationReport:
    from queris.evaluation_metrics import run_accuracy_evaluation
    from queris.evaluation_report import compose_evaluation_report
    from queris.evaluation_set import load_evaluation_set
    from queris.generation import SQLCorrectionContext
    from queris.safety_evaluation import evaluate_unsafe_queries
    from queris.schema import DatabaseSchema

    evaluation_set = load_evaluation_set("evals/retail_v1.json")
    subset = evaluation_set.model_copy(update={"cases": evaluation_set.cases[:2]})

    class ReferenceGenerator:
        def generate_sql(
            self,
            schema: DatabaseSchema,
            question: str,
            correction: SQLCorrectionContext | None = None,
        ) -> str:
            return next(case.expected_sql for case in subset.cases if case.question == question)

    outcomes = run_accuracy_evaluation(
        sample_database,
        subset,
        ReferenceGenerator(),
        sample_limit=0,
    )
    return compose_evaluation_report(
        subset,
        outcomes,
        evaluate_unsafe_queries(),
        generated_at=datetime(2026, 6, 22, tzinfo=UTC),
    )
