from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import queris.evaluation_metrics as evaluation_metrics
from queris.evaluation_metrics import (
    EvaluationOutcome,
    matches_evaluation_result,
    run_accuracy_evaluation,
    summarize_accuracy,
)
from queris.evaluation_set import EvaluationSet, EvaluationSetCase, load_evaluation_set
from queris.generation import SQLCorrectionContext
from queris.schema import DatabaseSchema
from queris.usage import GenerationUsage, TokenPricing

EVALUATION_SET_PATH = Path("evals/retail_v1.json")


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


class MixedGenerator(ReferenceGenerator):
    def __init__(self, evaluation_set: EvaluationSet) -> None:
        super().__init__(evaluation_set)
        self._sql_by_question = {
            evaluation_set.cases[0].question: evaluation_set.cases[0].expected_sql,
            evaluation_set.cases[1].question: "SELECT 1",
            evaluation_set.cases[2].question: "SELECT * FROM missing_table",
        }

    def generate_sql(
        self,
        schema: DatabaseSchema,
        question: str,
        correction: SQLCorrectionContext | None = None,
    ) -> str:
        return self._sql_by_question[question]


class OneRetryGenerator(ReferenceGenerator):
    def generate_sql(
        self,
        schema: DatabaseSchema,
        question: str,
        correction: SQLCorrectionContext | None = None,
    ) -> str:
        if correction is None:
            return "SELECT * FROM missing_table"
        return super().generate_sql(schema, question, correction)


class UsageReferenceGenerator(ReferenceGenerator):
    def __init__(self, evaluation_set: EvaluationSet) -> None:
        super().__init__(evaluation_set)
        self._usage = GenerationUsage()

    def generate_sql(
        self,
        schema: DatabaseSchema,
        question: str,
        correction: SQLCorrectionContext | None = None,
    ) -> str:
        self._usage += GenerationUsage(input_tokens=10, output_tokens=2, total_tokens=12)
        return super().generate_sql(schema, question, correction)

    def usage_snapshot(self) -> GenerationUsage:
        return self._usage


def _subset(evaluation_set: EvaluationSet, count: int) -> EvaluationSet:
    return evaluation_set.model_copy(update={"cases": evaluation_set.cases[:count]})


def test_reference_queries_produce_perfect_accuracy(sample_database: Path) -> None:
    evaluation_set = _subset(load_evaluation_set(EVALUATION_SET_PATH), 3)

    outcomes = run_accuracy_evaluation(
        sample_database,
        evaluation_set,
        ReferenceGenerator(evaluation_set),
        sample_limit=0,
    )
    metrics = summarize_accuracy(outcomes)

    assert metrics.total == 3
    assert metrics.execution_successes == 3
    assert metrics.correct_results == 3
    assert metrics.total_retries == 0
    assert metrics.execution_accuracy == 1
    assert metrics.result_accuracy == 1
    assert metrics.average_retry_count == 0
    assert metrics.p50_latency_ms >= 0
    assert metrics.p95_latency_ms >= metrics.p50_latency_ms
    assert metrics.total_tokens == 0
    assert metrics.estimated_cost_usd is None
    assert all(outcome.retry_count == 0 for outcome in outcomes)


def test_accuracy_distinguishes_wrong_results_from_failed_execution(
    sample_database: Path,
) -> None:
    evaluation_set = _subset(load_evaluation_set(EVALUATION_SET_PATH), 3)

    outcomes = run_accuracy_evaluation(
        sample_database,
        evaluation_set,
        MixedGenerator(evaluation_set),
        sample_limit=0,
        max_retries=0,
    )
    metrics = summarize_accuracy(outcomes)

    assert [outcome.execution_succeeded for outcome in outcomes] == [True, True, False]
    assert [outcome.result_correct for outcome in outcomes] == [True, False, False]
    assert outcomes[2].failure_stage == "execution"
    assert outcomes[2].retries_exhausted is True
    assert metrics.execution_accuracy == pytest.approx(2 / 3)
    assert metrics.result_accuracy == pytest.approx(1 / 3)


def test_retry_metrics_include_recovered_execution(sample_database: Path) -> None:
    evaluation_set = _subset(load_evaluation_set(EVALUATION_SET_PATH), 1)

    outcomes = run_accuracy_evaluation(
        sample_database,
        evaluation_set,
        OneRetryGenerator(evaluation_set),
        sample_limit=0,
    )
    metrics = summarize_accuracy(outcomes)

    assert outcomes[0].execution_succeeded is True
    assert outcomes[0].result_correct is True
    assert outcomes[0].retry_count == 1
    assert metrics.total_retries == 1
    assert metrics.average_retry_count == 1


def test_latency_metrics_use_monotonic_case_timings(
    sample_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation_set = _subset(load_evaluation_set(EVALUATION_SET_PATH), 3)
    readings = iter((1.0, 1.01, 2.0, 2.02, 3.0, 3.04))
    monkeypatch.setattr(evaluation_metrics, "perf_counter", lambda: next(readings))

    outcomes = run_accuracy_evaluation(
        sample_database,
        evaluation_set,
        ReferenceGenerator(evaluation_set),
        sample_limit=0,
    )
    metrics = summarize_accuracy(outcomes)

    assert [outcome.latency_ms for outcome in outcomes] == pytest.approx([10, 20, 40])
    assert metrics.p50_latency_ms == pytest.approx(20)
    assert metrics.p95_latency_ms == pytest.approx(38)


def test_usage_metrics_aggregate_tokens_and_explicit_cost(sample_database: Path) -> None:
    evaluation_set = _subset(load_evaluation_set(EVALUATION_SET_PATH), 2)
    pricing = TokenPricing(
        input_usd_per_million=Decimal("1"),
        output_usd_per_million=Decimal("2"),
    )

    outcomes = run_accuracy_evaluation(
        sample_database,
        evaluation_set,
        UsageReferenceGenerator(evaluation_set),
        sample_limit=0,
        pricing=pricing,
    )
    metrics = summarize_accuracy(outcomes)

    assert [outcome.usage.total_tokens for outcome in outcomes] == [12, 12]
    assert metrics.input_tokens == 20
    assert metrics.output_tokens == 4
    assert metrics.total_tokens == 24
    assert metrics.estimated_cost_usd == Decimal("0.000028")


def test_result_matching_allows_row_and_column_reordering() -> None:
    case = EvaluationSetCase(
        id="reordered-result",
        category="multi-table-join",
        question="Return regions and counts",
        expected_sql="SELECT name, 1 AS count FROM regions",
        expected_columns=("region_name", "order_count"),
        expected_rows=(("North", 2), ("South", 1)),
    )

    assert matches_evaluation_result(
        case,
        ("order_count", "region_name"),
        ((1, "South"), (2, "North")),
    )


def test_result_matching_rejects_wrong_values_and_shapes() -> None:
    case = load_evaluation_set(EVALUATION_SET_PATH).cases[0]

    assert not matches_evaluation_result(case, ("count",), ((999,),))
    assert not matches_evaluation_result(case, ("one", "two"), ((4, 4),))


def test_result_matching_accepts_json_date_representations() -> None:
    case = EvaluationSetCase(
        id="dated-result",
        category="time-filtering",
        question="Return the first order date",
        expected_sql="SELECT MIN(order_date) FROM orders",
        expected_columns=("order_date",),
        expected_rows=(("2026-01-15",),),
    )

    assert matches_evaluation_result(case, ("order_date",), ((date(2026, 1, 15),),))


def test_summary_handles_no_attempted_cases() -> None:
    metrics = summarize_accuracy(())

    assert metrics.total == 0
    assert metrics.total_retries == 0
    assert metrics.execution_accuracy == 0
    assert metrics.result_accuracy == 0
    assert metrics.average_retry_count == 0
    assert metrics.p50_latency_ms == 0
    assert metrics.p95_latency_ms == 0
    assert metrics.total_tokens == 0
    assert metrics.estimated_cost_usd is None


def test_correct_result_requires_successful_execution() -> None:
    with pytest.raises(ValueError, match="successful execution"):
        EvaluationOutcome(
            case_id="invalid-outcome",
            category="simple-aggregation",
            question="Question?",
            execution_succeeded=False,
            result_correct=True,
            retry_count=0,
            latency_ms=0,
        )
