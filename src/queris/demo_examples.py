"""Curated question starters for the online retail demo."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ExampleCategory = Literal[
    "revenue",
    "orders",
    "products",
    "customers",
    "pricing",
    "cancellations",
    "time-series",
    "countries",
    "quality",
    "discovery",
]
ChartKind = Literal["bar", "line", "metric", "table"]


class DemoExample(BaseModel):
    """One safe, clickable natural-language question starter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    question: str
    category: ExampleCategory
    tables: tuple[str, ...] = Field(min_length=1)
    chart: ChartKind


class DemoHistoryItem(BaseModel):
    """A transparent, not-yet-executed demo history entry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source: Literal["demo"]
    created_at: str
    user: str
    question: str
    status: Literal["ready_to_run"]
    tables: tuple[str, ...]
    chart: ChartKind
    explanation: str
    result_summary: str
    sql: None = None


_GROUPS: tuple[tuple[str, str, str, tuple[str, ...], ChartKind], ...] = (
    (
        "revenue",
        "Revenue",
        "What was total revenue {suffix}?",
        ("orders", "order_items"),
        "metric",
    ),
    (
        "orders",
        "Orders",
        "How many orders were placed {suffix}?",
        ("orders",),
        "metric",
    ),
    (
        "products",
        "Products",
        "Which products {suffix}?",
        ("products", "order_items", "orders"),
        "bar",
    ),
    (
        "customers",
        "Customers",
        "Which customers {suffix}?",
        ("customers", "orders", "order_items"),
        "bar",
    ),
    (
        "pricing",
        "Pricing",
        "What is the average unit price {suffix}?",
        ("order_items", "orders"),
        "bar",
    ),
    (
        "cancellations",
        "Cancellations",
        "What is the cancellation rate {suffix}?",
        ("orders",),
        "metric",
    ),
    (
        "time-series",
        "Time series",
        "How did revenue change {suffix}?",
        ("orders", "order_items"),
        "line",
    ),
    (
        "countries",
        "Countries",
        "Which countries {suffix}?",
        ("orders", "order_items"),
        "bar",
    ),
    (
        "quality",
        "Data quality",
        "Show the data quality profile {suffix}.",
        ("orders", "order_items", "products", "customers"),
        "table",
    ),
    (
        "discovery",
        "Discovery",
        "Give me a useful overview {suffix}.",
        ("orders", "order_items", "products", "customers"),
        "table",
    ),
)

_SUFFIXES: tuple[str, ...] = (
    "by country",
    "by product",
    "by month",
    "by customer",
    "for the United Kingdom",
    "for cancelled invoices",
    "excluding cancelled invoices",
    "for orders above the median order value",
    "for products priced above £10",
    "for the first quarter of the source period",
)


def get_demo_examples() -> tuple[DemoExample, ...]:
    """Return exactly 100 deterministic examples for the frontend catalog."""
    examples = tuple(
        DemoExample(
            id=f"{category}-{index + 1:02d}",
            title=f"{label}: {suffix.removeprefix('for ').capitalize()}",
            question=question.format(suffix=suffix),
            category=category,
            tables=tables,
            chart=chart,
        )
        for category, label, question, tables, chart in _GROUPS
        for index, suffix in enumerate(_SUFFIXES)
    )
    return examples


def get_demo_history() -> tuple[DemoHistoryItem, ...]:
    """Return a stable demo history without fabricating executed results."""
    return tuple(
        DemoHistoryItem(
            id=f"history-{example.id}",
            source="demo",
            created_at=f"2026-09-{(index % 28) + 1:02d}T09:00:00Z",
            user="Queris demo",
            question=example.question,
            status="ready_to_run",
            tables=example.tables,
            chart=example.chart,
            explanation=(
                "Starter preparado para explorar el dataset Online Retail. "
                "Al ejecutarlo, Queris generará y validará el SQL de solo lectura."
            ),
            result_summary="Listo para ejecutar · todavía no materializado",
        )
        for index, example in enumerate(get_demo_examples(), start=1)
    )
