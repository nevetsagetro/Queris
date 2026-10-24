"""Privacy-preserving local query and generation metrics."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from queris.usage import GenerationUsage, TokenPricing


class MetricsEvent(BaseModel):
    """One operational event without question, SQL, rows, paths, or credentials."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    recorded_at: datetime
    mode: Literal["llm", "cache", "demo"]
    status: str
    cache_hit: bool
    retry_count: int = Field(ge=0)
    latency_ms: float = Field(ge=0)
    usage: GenerationUsage = GenerationUsage()


class MetricsSummary(BaseModel):
    """Aggregated local metrics safe to expose to the frontend."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_count: int = Field(ge=0)
    llm_count: int = Field(ge=0)
    cache_hits: int = Field(ge=0)
    demo_count: int = Field(ge=0)
    total_retries: int = Field(ge=0)
    total_latency_ms: float = Field(ge=0)
    usage: GenerationUsage
    estimated_cost_usd: str | None = None


class MetricsLedger:
    """Append-only local ledger for operational counts."""

    def __init__(self, path: str | Path | None):
        self.path = Path(path).expanduser().resolve() if path is not None else None

    def record(self, event: MetricsEvent) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")

    def summary(self, pricing: TokenPricing | None = None) -> MetricsSummary:
        events = self._events()
        usage = GenerationUsage()
        for event in events:
            usage += event.usage
        estimated = str(pricing.estimate_cost(usage)) if pricing is not None else None
        return MetricsSummary(
            query_count=len(events),
            llm_count=sum(event.mode == "llm" for event in events),
            cache_hits=sum(event.cache_hit for event in events),
            demo_count=sum(event.mode == "demo" for event in events),
            total_retries=sum(event.retry_count for event in events),
            total_latency_ms=round(sum(event.latency_ms for event in events), 3),
            usage=usage,
            estimated_cost_usd=estimated,
        )

    def _events(self) -> list[MetricsEvent]:
        if self.path is None or not self.path.is_file():
            return []
        events: list[MetricsEvent] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(MetricsEvent.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValueError):
                continue
        return events


def now_utc() -> datetime:
    """Return a timezone-aware timestamp for a metrics event."""
    return datetime.now(UTC)
