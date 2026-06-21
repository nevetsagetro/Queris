from pathlib import Path

import pytest

from queris.pipeline import run_text_to_sql
from queris.schema import DatabaseSchema
from queris.sql_validation import SQLValidationError


class FakeGenerator:
    def __init__(self, sql: str) -> None:
        self.sql = sql
        self.calls: list[tuple[DatabaseSchema, str]] = []

    def generate_sql(self, schema: DatabaseSchema, question: str) -> str:
        self.calls.append((schema, question))
        return self.sql


def test_run_text_to_sql_executes_generated_query(sample_database: Path) -> None:
    generator = FakeGenerator(
        """
        SELECT r.name AS region, COUNT(*) AS order_count
        FROM orders AS o
        JOIN regions AS r ON r.region_id = o.region_id
        GROUP BY r.name
        ORDER BY r.name
        """
    )

    result = run_text_to_sql(
        sample_database,
        "  How many orders are in each region?  ",
        generator,
        sample_limit=0,
    )

    assert result.question == "How many orders are in each region?"
    assert result.sql == generator.sql
    assert result.columns == ("region", "order_count")
    assert result.rows == (("North", 2), ("South", 1), ("West", 1))
    schema, question = generator.calls[0]
    assert [table.name for table in schema.tables] == [
        "categories",
        "order_items",
        "orders",
        "products",
        "regions",
    ]
    assert question == result.question


@pytest.mark.parametrize(
    "unsafe_sql",
    [
        "DROP TABLE orders",
        "SELECT COUNT(*) FROM orders; DROP TABLE orders",
    ],
)
def test_run_text_to_sql_rejects_unsafe_generated_sql(
    sample_database: Path,
    unsafe_sql: str,
) -> None:
    generator = FakeGenerator(unsafe_sql)

    with pytest.raises(SQLValidationError):
        run_text_to_sql(sample_database, "Delete all orders", generator)


@pytest.mark.parametrize("question", ["", "   "])
def test_run_text_to_sql_rejects_empty_question(
    sample_database: Path,
    question: str,
) -> None:
    generator = FakeGenerator("SELECT 1")

    with pytest.raises(ValueError, match="question"):
        run_text_to_sql(sample_database, question, generator)

    assert generator.calls == []


def test_run_text_to_sql_rejects_non_string_question(sample_database: Path) -> None:
    generator = FakeGenerator("SELECT 1")

    with pytest.raises(TypeError, match="question"):
        run_text_to_sql(sample_database, None, generator)  # type: ignore[arg-type]

    assert generator.calls == []
