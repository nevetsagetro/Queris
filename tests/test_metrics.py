from datetime import UTC, datetime

from queris.metrics import MetricsEvent, MetricsLedger
from queris.usage import GenerationUsage


def test_metrics_ledger_aggregates_without_sensitive_fields(tmp_path) -> None:
    ledger = MetricsLedger(tmp_path / "metrics.jsonl")
    ledger.record(
        MetricsEvent(
            recorded_at=datetime.now(UTC),
            mode="llm",
            status="success",
            cache_hit=False,
            retry_count=1,
            latency_ms=12.5,
            usage=GenerationUsage(input_tokens=100, output_tokens=20, total_tokens=120),
        )
    )
    ledger.record(
        MetricsEvent(
            recorded_at=datetime.now(UTC),
            mode="cache",
            status="success",
            cache_hit=True,
            retry_count=0,
            latency_ms=2,
        )
    )

    summary = ledger.summary()
    raw = (tmp_path / "metrics.jsonl").read_text(encoding="utf-8")
    assert summary.query_count == 2
    assert summary.cache_hits == 1
    assert summary.usage.total_tokens == 120
    assert "question" not in raw
    assert "sql" not in raw
