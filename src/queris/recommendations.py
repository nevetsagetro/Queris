"""Deterministic question recommendations derived from the active catalog."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from queris.demo_examples import get_demo_examples
from queris.schema import DatabaseSchema


class RecommendedRun(BaseModel):
    """One safe, explainable question suggestion for the active dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    demo_id: str
    question: str
    reason: str
    tables: tuple[str, ...]
    chart: Literal["bar", "line", "metric", "table"]
    priority: int = Field(ge=1)


def recommend_runs(schema: DatabaseSchema, limit: int = 12) -> tuple[RecommendedRun, ...]:
    """Select varied, executable starters whose referenced tables exist."""
    table_names = {table.name for table in schema.tables}
    preferred_ids = (
        "revenue-03",
        "revenue-01",
        "orders-03",
        "countries-01",
        "products-02",
        "customers-04",
        "cancellations-01",
        "quality-01",
        "discovery-01",
    )
    reasons = {
        "revenue": "A core measure is available with a useful business dimension.",
        "orders": "Order volume is a good baseline for understanding dataset scale.",
        "countries": "A geographic dimension is available for comparison.",
        "products": "Product-level results reveal concentration and long-tail behavior.",
        "customers": "Customer-level aggregation supports retention and value discovery.",
        "cancellations": "Cancellation fields support a data-quality and operations check.",
        "quality": "A bounded quality check shows missingness and table health.",
        "discovery": "A compact overview helps orient a first-time user.",
    }
    examples = {example.id: example for example in get_demo_examples()}
    selected: list[RecommendedRun] = []
    for priority, demo_id in enumerate(preferred_ids, start=1):
        example = examples.get(demo_id)
        if example is None or not set(example.tables) & table_names:
            continue
        selected.append(
            RecommendedRun(
                id=f"recommendation-{demo_id}",
                demo_id=demo_id,
                question=example.question,
                reason=reasons.get(example.category, "Curated for the active catalog."),
                tables=tuple(table for table in example.tables if table in table_names),
                chart=example.chart,
                priority=priority,
            )
        )
        if len(selected) >= limit:
            break
    if not selected:
        for priority, table_name in enumerate(sorted(table_names), start=1):
            selected.append(
                RecommendedRun(
                    id=f"recommendation-table-count-{table_name}",
                    demo_id=f"table-count:{table_name}",
                    question=f"How many rows are in {table_name}?",
                    reason="A row-count baseline is the safest first analysis for a new dataset.",
                    tables=(table_name,),
                    chart="metric",
                    priority=priority,
                )
            )
            if len(selected) >= limit:
                break
    return tuple(selected)
