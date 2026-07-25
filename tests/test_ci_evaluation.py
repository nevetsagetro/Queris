from queris.adversarial_evaluation import AdversarialSummary
from queris.ci_evaluation import assess_ci_evaluation
from queris.evaluation_metrics import AccuracyMetrics
from queris.safety_evaluation import UnsafeQueryMetrics


def passing_metrics() -> tuple[AccuracyMetrics, UnsafeQueryMetrics, AdversarialSummary]:
    accuracy = AccuracyMetrics(
        total=50,
        execution_successes=50,
        correct_results=50,
        total_retries=0,
        execution_accuracy=1,
        result_accuracy=1,
        average_retry_count=0,
        p50_latency_ms=1,
        p95_latency_ms=2,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
    )
    safety = UnsafeQueryMetrics(
        total=24,
        blocked=24,
        blocked_unsafe_query_rate=1,
    )
    adversarial = AdversarialSummary(
        total=27,
        passed_cases=27,
        pass_rate=1,
        safety_cases=12,
        blocked_safety_cases=12,
        block_rate=1,
        passed=True,
    )
    return accuracy, safety, adversarial


def test_ci_evaluation_accepts_strict_phase_6_and_7_thresholds() -> None:
    result = assess_ci_evaluation(*passing_metrics())

    assert result.passed is True
    assert result.failures == ()


def test_ci_evaluation_fails_when_validator_allows_an_unsafe_case() -> None:
    accuracy, safety, adversarial = passing_metrics()
    unsafe_regression = safety.model_copy(
        update={
            "blocked": safety.blocked - 1,
            "blocked_unsafe_query_rate": (safety.blocked - 1) / safety.total,
        }
    )

    result = assess_ci_evaluation(accuracy, unsafe_regression, adversarial)

    assert result.passed is False
    assert result.failures == ("Phase 6 blocked unsafe query rate is 95.8%",)


def test_ci_evaluation_rejects_missing_versioned_cases() -> None:
    accuracy, safety, adversarial = passing_metrics()

    result = assess_ci_evaluation(
        accuracy.model_copy(update={"total": 49}),
        safety,
        adversarial,
    )

    assert result.passed is False
    assert result.failures == ("Phase 6 case count 49 is below 50",)
