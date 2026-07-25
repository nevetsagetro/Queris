"""Pure presentation helpers for the Streamlit demo."""

from numbers import Real
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from queris.agent_loop import AgentQueryResult


class ChartSpec(BaseModel):
    """One chart supported by the demo result renderer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["bar"]
    x: str
    y: tuple[str, ...]


class DemoPresentation(BaseModel):
    """UI-ready records, visualization, and explanation for a successful query."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)

    records: tuple[dict[str, Any], ...]
    chart: ChartSpec | None
    explanation: str


def present_success(result: AgentQueryResult) -> DemoPresentation:
    """Convert a successful agent result into deterministic demo content."""
    if result.status != "success":
        raise ValueError("only successful query results can be presented")

    records = tuple(dict(zip(result.columns, row, strict=True)) for row in result.rows)
    chart = _choose_chart(result.columns, result.rows)
    if chart is not None and chart.x == "_row":
        records = tuple({"_row": index, **record} for index, record in enumerate(records, start=1))
    return DemoPresentation(
        records=records,
        chart=chart,
        explanation=_explain_result(result),
    )


def _choose_chart(
    columns: tuple[str, ...],
    rows: tuple[tuple[Any, ...], ...],
) -> ChartSpec | None:
    if not rows:
        return None
    numeric_columns = tuple(
        column for index, column in enumerate(columns) if _column_is_numeric(rows, index)
    )
    if not numeric_columns:
        return None
    category_columns = tuple(column for column in columns if column not in numeric_columns)
    return ChartSpec(
        kind="bar",
        x=category_columns[0] if category_columns else "_row",
        y=numeric_columns,
    )


def _column_is_numeric(rows: tuple[tuple[Any, ...], ...], index: int) -> bool:
    values = tuple(row[index] for row in rows if row[index] is not None)
    return bool(values) and all(
        isinstance(value, Real) and not isinstance(value, bool) for value in values
    )


def _explain_result(result: AgentQueryResult) -> str:
    row_count = len(result.rows)
    if row_count == 0:
        return "The query completed successfully but returned no matching rows."
    if row_count == 1 and len(result.columns) == 1:
        return f"The result is {result.rows[0][0]} for {result.columns[0]}."
    row_label = "row" if row_count == 1 else "rows"
    columns = ", ".join(result.columns)
    return f"The query returned {row_count} {row_label} across these fields: {columns}."
