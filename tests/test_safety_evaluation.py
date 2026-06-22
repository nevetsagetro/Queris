import pytest

from queris.safety_evaluation import (
    UNSAFE_QUERY_CASES,
    UnsafeQueryCase,
    UnsafeQueryOutcome,
    evaluate_unsafe_queries,
    summarize_unsafe_queries,
)


def test_reviewed_unsafe_queries_are_unique_and_all_blocked() -> None:
    outcomes = evaluate_unsafe_queries()
    metrics = summarize_unsafe_queries(outcomes)

    assert len(UNSAFE_QUERY_CASES) == 24
    assert len({case.id for case in UNSAFE_QUERY_CASES}) == 24
    assert all(outcome.blocked and outcome.error for outcome in outcomes)
    assert metrics.total == 24
    assert metrics.blocked == 24
    assert metrics.blocked_unsafe_query_rate == 1


def test_blocked_rate_exposes_an_unblocked_query() -> None:
    cases = (
        UnsafeQueryCase(id="unsafe", sql="DROP TABLE events"),
        UnsafeQueryCase(id="allowed", sql="SELECT 1"),
    )

    outcomes = evaluate_unsafe_queries(cases)
    metrics = summarize_unsafe_queries(outcomes)

    assert [outcome.blocked for outcome in outcomes] == [True, False]
    assert metrics.blocked == 1
    assert metrics.blocked_unsafe_query_rate == 0.5


def test_blocked_rate_handles_no_attempted_queries() -> None:
    metrics = summarize_unsafe_queries(())

    assert metrics.total == 0
    assert metrics.blocked == 0
    assert metrics.blocked_unsafe_query_rate == 0


def test_blocked_outcome_requires_validation_diagnostic() -> None:
    with pytest.raises(ValueError, match="validation diagnostic"):
        UnsafeQueryOutcome(
            case_id="invalid",
            sql="DROP TABLE events",
            blocked=True,
        )
