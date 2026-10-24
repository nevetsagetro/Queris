"""Typed registry connecting demo metadata with prepared SQL builders."""

from collections.abc import Callable
from dataclasses import dataclass

from queris.demo_examples import DemoExample, get_demo_examples
from queris.demo_queries import build_generic_query, build_revenue_query

SQLBuilder = Callable[[int], str]


@dataclass(frozen=True)
class DemoDefinition:
    """Complete executable definition for one curated demo question."""

    example: DemoExample
    variant: int
    sql_builder: SQLBuilder


def get_demo_registry() -> tuple[DemoDefinition, ...]:
    """Return all demos with metadata and their domain-specific SQL builder."""
    definitions: list[DemoDefinition] = []
    for position, example in enumerate(get_demo_examples()):
        variant = position % 10 + 1
        builder = (
            build_revenue_query
            if example.category == "revenue"
            else lambda _variant, category=example.category: build_generic_query(category)
        )
        definitions.append(DemoDefinition(example, variant, builder))
    return tuple(definitions)


def get_demo_definition(example_id: str) -> DemoDefinition | None:
    """Resolve a stable demo identifier without interpreting its string format."""
    return next((item for item in get_demo_registry() if item.example.id == example_id), None)
