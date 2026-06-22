"""One-command Phase 6 evaluation report generation."""

import argparse
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from queris.agent_loop import DEFAULT_MAX_RETRIES
from queris.evaluation_metrics import (
    AccuracyMetrics,
    EvaluationOutcome,
    run_accuracy_evaluation,
    summarize_accuracy,
)
from queris.evaluation_set import EvaluationSet, load_evaluation_set
from queris.generation import GeminiSQLGenerator
from queris.safety_evaluation import (
    UnsafeQueryMetrics,
    UnsafeQueryOutcome,
    evaluate_unsafe_queries,
    summarize_unsafe_queries,
)
from queris.usage import TokenPricing


class EvaluationReport(BaseModel):
    """Versioned aggregate and audit details for one Phase 6 run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal[1] = 1
    generated_at: datetime
    dataset_id: str
    fixture: str
    accuracy: AccuracyMetrics
    safety: UnsafeQueryMetrics
    outcomes: tuple[EvaluationOutcome, ...]
    unsafe_query_outcomes: tuple[UnsafeQueryOutcome, ...]


def compose_evaluation_report(
    evaluation_set: EvaluationSet,
    outcomes: tuple[EvaluationOutcome, ...],
    unsafe_query_outcomes: tuple[UnsafeQueryOutcome, ...],
    *,
    generated_at: datetime | None = None,
) -> EvaluationReport:
    """Compose one versioned report from existing accuracy and safety outcomes."""
    return EvaluationReport(
        generated_at=generated_at or datetime.now(UTC),
        dataset_id=evaluation_set.dataset_id,
        fixture=evaluation_set.fixture,
        accuracy=summarize_accuracy(outcomes),
        safety=summarize_unsafe_queries(unsafe_query_outcomes),
        outcomes=outcomes,
        unsafe_query_outcomes=unsafe_query_outcomes,
    )


def format_evaluation_table(report: EvaluationReport) -> str:
    """Render the report metrics as a compact human-readable ASCII table."""
    cost = report.accuracy.estimated_cost_usd
    rows = (
        ("Cases", str(report.accuracy.total)),
        ("Execution accuracy", _percentage(report.accuracy.execution_accuracy)),
        ("Result accuracy", _percentage(report.accuracy.result_accuracy)),
        ("Blocked unsafe queries", _percentage(report.safety.blocked_unsafe_query_rate)),
        ("Average retries", f"{report.accuracy.average_retry_count:.2f}"),
        ("Latency p50", f"{report.accuracy.p50_latency_ms:.2f} ms"),
        ("Latency p95", f"{report.accuracy.p95_latency_ms:.2f} ms"),
        ("Input tokens", str(report.accuracy.input_tokens)),
        ("Output tokens", str(report.accuracy.output_tokens)),
        ("Total tokens", str(report.accuracy.total_tokens)),
        ("Estimated cost", f"${cost:f}" if cost is not None else "n/a"),
    )
    metric_width = max(len("Metric"), *(len(metric) for metric, _ in rows))
    value_width = max(len("Value"), *(len(value) for _, value in rows))
    separator = f"+-{'-' * metric_width}-+-{'-' * value_width}-+"
    lines = [
        separator,
        f"| {'Metric':<{metric_width}} | {'Value':<{value_width}} |",
        separator,
    ]
    lines.extend(f"| {metric:<{metric_width}} | {value:<{value_width}} |" for metric, value in rows)
    lines.append(separator)
    return "\n".join(lines)


def write_evaluation_report(path: str | Path, report: EvaluationReport) -> Path:
    """Write one structured JSON report, replacing an earlier run at the same path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return output_path


def _percentage(value: float) -> str:
    return f"{value:.1%}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the full Queris Phase 6 evaluation")
    parser.add_argument("database", type=Path, help="Existing retail .duckdb path")
    parser.add_argument(
        "--questions",
        type=Path,
        default=Path("evals/retail_v1.json"),
        help="Versioned Phase 6 evaluation set JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/results/phase6.json"),
        help="Ignored local structured JSON report",
    )
    parser.add_argument("--samples", type=int, default=3, help="Sample values per column")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Maximum correction retries per question",
    )
    parser.add_argument(
        "--input-usd-per-million",
        type=Decimal,
        help="Explicit input-token rate used for cost estimation",
    )
    parser.add_argument(
        "--output-usd-per-million",
        type=Decimal,
        help="Explicit output-token rate used for cost estimation",
    )
    return parser


def _pricing_from_args(
    parser: argparse.ArgumentParser,
    input_rate: Decimal | None,
    output_rate: Decimal | None,
) -> TokenPricing | None:
    if (input_rate is None) != (output_rate is None):
        parser.error("both token rate arguments must be provided together")
    if input_rate is None or output_rate is None:
        return None
    try:
        return TokenPricing(
            input_usd_per_million=input_rate,
            output_usd_per_million=output_rate,
        )
    except ValueError as error:
        parser.error(str(error))


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    pricing = _pricing_from_args(
        parser,
        args.input_usd_per_million,
        args.output_usd_per_million,
    )
    evaluation_set = load_evaluation_set(args.questions)
    outcomes = run_accuracy_evaluation(
        args.database,
        evaluation_set,
        GeminiSQLGenerator(),
        sample_limit=args.samples,
        max_retries=args.max_retries,
        pricing=pricing,
    )
    unsafe_query_outcomes = evaluate_unsafe_queries()
    report = compose_evaluation_report(evaluation_set, outcomes, unsafe_query_outcomes)
    output_path = write_evaluation_report(args.output, report)
    print(format_evaluation_table(report))
    print(f"JSON report: {output_path}")


if __name__ == "__main__":
    main()
