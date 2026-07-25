"""Historical storage and regression comparison for Phase 6 reports."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from queris.evaluation_report import EvaluationReport

MetricDirection = Literal["higher", "lower"]
MetricValue = float | int | Decimal


class MetricComparison(BaseModel):
    """One current-versus-previous metric comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str
    previous: MetricValue
    current: MetricValue
    delta: MetricValue
    preferred: MetricDirection
    regressed: bool


class EvaluationComparison(BaseModel):
    """Comparable metric changes between two compatible Phase 6 reports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    previous_generated_at: datetime
    current_generated_at: datetime
    metrics: tuple[MetricComparison, ...]

    @property
    def has_regressions(self) -> bool:
        """Return whether any comparable metric moved in the wrong direction."""
        return any(metric.regressed for metric in self.metrics)


def write_historical_report(directory: str | Path, report: EvaluationReport) -> Path:
    """Append one immutable timestamped report to a local history directory."""
    history_directory = Path(directory)
    history_directory.mkdir(parents=True, exist_ok=True)
    timestamp = report.generated_at.strftime("%Y%m%dT%H%M%S.%fZ")
    candidate = history_directory / f"{timestamp}-{report.dataset_id}.json"
    suffix = 2
    while candidate.exists():
        candidate = history_directory / f"{timestamp}-{report.dataset_id}-{suffix}.json"
        suffix += 1
    candidate.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return candidate


def load_latest_compatible_report(
    directory: str | Path,
    current: EvaluationReport,
) -> EvaluationReport | None:
    """Load the newest prior report with the same evaluation and safety cases."""
    history_directory = Path(directory)
    if not history_directory.exists():
        return None
    reports = tuple(
        report
        for path in history_directory.glob("*.json")
        if (report := _load_report(path)) is not None
    )
    compatible = (
        report
        for report in reports
        if _reports_are_compatible(report, current) and report.generated_at < current.generated_at
    )
    return max(compatible, key=lambda report: report.generated_at, default=None)


def compare_evaluation_reports(
    previous: EvaluationReport,
    current: EvaluationReport,
) -> EvaluationComparison:
    """Compare compatible reports using explicit metric direction semantics."""
    if not _reports_are_compatible(previous, current):
        raise ValueError("evaluation reports have incompatible datasets or case sets")
    metrics = [
        _comparison(
            "Execution accuracy",
            previous.accuracy.execution_accuracy,
            current.accuracy.execution_accuracy,
            "higher",
        ),
        _comparison(
            "Result accuracy",
            previous.accuracy.result_accuracy,
            current.accuracy.result_accuracy,
            "higher",
        ),
        _comparison(
            "Blocked unsafe queries",
            previous.safety.blocked_unsafe_query_rate,
            current.safety.blocked_unsafe_query_rate,
            "higher",
        ),
        _comparison(
            "Average retries",
            previous.accuracy.average_retry_count,
            current.accuracy.average_retry_count,
            "lower",
        ),
        _comparison(
            "Latency p50 ms",
            previous.accuracy.p50_latency_ms,
            current.accuracy.p50_latency_ms,
            "lower",
        ),
        _comparison(
            "Latency p95 ms",
            previous.accuracy.p95_latency_ms,
            current.accuracy.p95_latency_ms,
            "lower",
        ),
        _comparison(
            "Total tokens",
            previous.accuracy.total_tokens,
            current.accuracy.total_tokens,
            "lower",
        ),
    ]
    if (
        previous.accuracy.estimated_cost_usd is not None
        and current.accuracy.estimated_cost_usd is not None
    ):
        metrics.append(
            _comparison(
                "Estimated cost USD",
                previous.accuracy.estimated_cost_usd,
                current.accuracy.estimated_cost_usd,
                "lower",
            )
        )
    return EvaluationComparison(
        previous_generated_at=previous.generated_at,
        current_generated_at=current.generated_at,
        metrics=tuple(metrics),
    )


def format_comparison_table(comparison: EvaluationComparison) -> str:
    """Render historical metric deltas as a compact ASCII table."""
    rows = tuple(
        (
            metric.metric,
            _format_value(metric.previous),
            _format_value(metric.current),
            _format_delta(metric.delta),
            "REGRESSION" if metric.regressed else "ok",
        )
        for metric in comparison.metrics
    )
    headers = ("Metric", "Previous", "Current", "Delta", "Status")
    widths = tuple(
        max(len(header), *(len(row[index]) for row in rows)) for index, header in enumerate(headers)
    )
    separator = "+" + "+".join(f"-{'-' * width}-" for width in widths) + "+"
    lines = [
        separator,
        "|"
        + "|".join(f" {header:<{width}} " for header, width in zip(headers, widths, strict=True))
        + "|",
        separator,
    ]
    lines.extend(
        "|"
        + "|".join(f" {value:<{width}} " for value, width in zip(row, widths, strict=True))
        + "|"
        for row in rows
    )
    lines.append(separator)
    return "\n".join(lines)


def _load_report(path: Path) -> EvaluationReport | None:
    try:
        return EvaluationReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return None


def _reports_are_compatible(left: EvaluationReport, right: EvaluationReport) -> bool:
    return (
        left.format_version == right.format_version
        and left.dataset_id == right.dataset_id
        and left.fixture == right.fixture
        and tuple(outcome.case_id for outcome in left.outcomes)
        == tuple(outcome.case_id for outcome in right.outcomes)
        and tuple(outcome.case_id for outcome in left.unsafe_query_outcomes)
        == tuple(outcome.case_id for outcome in right.unsafe_query_outcomes)
        and tuple(outcome.case_id for outcome in left.adversarial_outcomes)
        == tuple(outcome.case_id for outcome in right.adversarial_outcomes)
    )


def _comparison(
    metric: str,
    previous: MetricValue,
    current: MetricValue,
    preferred: MetricDirection,
) -> MetricComparison:
    delta = current - previous
    return MetricComparison(
        metric=metric,
        previous=previous,
        current=current,
        delta=delta,
        preferred=preferred,
        regressed=delta < 0 if preferred == "higher" else delta > 0,
    )


def _format_value(value: MetricValue) -> str:
    return f"{value:.6g}"


def _format_delta(value: MetricValue) -> str:
    return f"{value:+.6g}"
