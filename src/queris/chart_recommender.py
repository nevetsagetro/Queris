"""Explainable chart recommendations for tabular query results."""

from numbers import Number
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ChartName = Literal["bar", "line", "scatter", "metric", "table"]


class ChartRecommendation(BaseModel):
    """One deterministic recommendation with an inspectable rationale."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chart: ChartName
    confidence: float = Field(ge=0, le=1)
    x_field: str | None = None
    y_field: str | None = None
    reason: str


def recommend_chart(
    columns: tuple[str, ...], rows: tuple[tuple[Any, ...], ...]
) -> ChartRecommendation:
    """Recommend the smallest useful chart based on result shape and values."""
    if not columns or not rows:
        return ChartRecommendation(
            chart="table", confidence=0.99, reason="The result has no chartable rows."
        )
    numeric = [index for index in range(len(columns)) if _numeric_column(rows, index)]
    temporal = next((index for index, name in enumerate(columns) if _is_temporal_name(name)), None)
    if temporal is not None and numeric:
        y_index = (
            numeric[0] if numeric[0] != temporal else (numeric[1] if len(numeric) > 1 else None)
        )
        if y_index is not None:
            return ChartRecommendation(
                chart="line",
                confidence=0.94,
                x_field=columns[temporal],
                y_field=columns[y_index],
                reason="The result contains a temporal dimension and a numeric measure.",
            )
    if len(numeric) >= 2:
        return ChartRecommendation(
            chart="scatter",
            confidence=0.82,
            x_field=columns[numeric[0]],
            y_field=columns[numeric[1]],
            reason="The result contains two numeric measures suitable for comparison.",
        )
    if len(numeric) == 1 and len(columns) == 1:
        return ChartRecommendation(
            chart="metric",
            confidence=0.98,
            y_field=columns[numeric[0]],
            reason="The result contains one numeric value, so a KPI is the clearest view.",
        )
    if len(columns) >= 2 and len(numeric) == 1:
        return ChartRecommendation(
            chart="bar",
            confidence=0.9,
            x_field=columns[0],
            y_field=columns[numeric[0]],
            reason="The result contains a category and one numeric measure.",
        )
    return ChartRecommendation(
        chart="table", confidence=0.9, reason="The result shape is better inspected as a table."
    )


def _numeric_column(rows: tuple[tuple[Any, ...], ...], index: int) -> bool:
    values = [row[index] for row in rows if len(row) > index and row[index] is not None]
    return bool(values) and all(
        isinstance(value, Number) and not isinstance(value, bool) for value in values
    )


def _is_temporal_name(name: str) -> bool:
    lowered = name.casefold()
    return any(token in lowered for token in ("date", "time", "month", "year", "week", "day"))
