from pathlib import Path

import pytest

from queris.database import read_only_connection
from queris.pipeline import FullSchemaSelector, RetrievedSchemaSelector, run_text_to_sql
from queris.schema import DatabaseSchema, introspect_schema
from queris.schema_retrieval import SchemaMatch
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
        FullSchemaSelector(),
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
        run_text_to_sql(
            sample_database,
            "Delete all orders",
            generator,
            FullSchemaSelector(),
        )


@pytest.mark.parametrize("question", ["", "   "])
def test_run_text_to_sql_rejects_empty_question(
    sample_database: Path,
    question: str,
) -> None:
    generator = FakeGenerator("SELECT 1")

    with pytest.raises(ValueError, match="question"):
        run_text_to_sql(sample_database, question, generator, FullSchemaSelector())

    assert generator.calls == []


def test_run_text_to_sql_rejects_non_string_question(sample_database: Path) -> None:
    generator = FakeGenerator("SELECT 1")

    with pytest.raises(TypeError, match="question"):
        run_text_to_sql(  # type: ignore[arg-type]
            sample_database,
            None,
            generator,
            FullSchemaSelector(),
        )

    assert generator.calls == []


class FakeRetriever:
    def __init__(self, matches: tuple[SchemaMatch, ...]) -> None:
        self.matches = matches
        self.questions: list[str] = []

    def retrieve(self, question: str) -> tuple[SchemaMatch, ...]:
        self.questions.append(question)
        return self.matches


def _match(
    table_name: str,
    *,
    column_name: str | None = None,
) -> SchemaMatch:
    return SchemaMatch(
        kind="column" if column_name else "table",
        schema_name="main",
        table_name=table_name,
        column_name=column_name,
        document_text="{}",
        similarity=1.0,
    )


def test_run_text_to_sql_excludes_irrelevant_schema_from_generation(
    sample_database: Path,
) -> None:
    generator = FakeGenerator("SELECT COUNT(*) FROM orders")
    retriever = FakeRetriever((_match("orders"),))

    result = run_text_to_sql(
        sample_database,
        "How many orders are there?",
        generator,
        RetrievedSchemaSelector(retriever),
        sample_limit=0,
    )

    selected_schema, question = generator.calls[0]
    assert [table.name for table in selected_schema.tables] == ["orders"]
    assert [column.name for column in selected_schema.tables[0].columns] == [
        "order_id",
        "order_date",
        "region_id",
    ]
    assert retriever.questions == [question]
    assert result.rows == ((4,),)


def test_retrieved_schema_selector_keeps_only_live_matched_columns(
    sample_database: Path,
) -> None:
    with read_only_connection(sample_database) as connection:
        schema = introspect_schema(connection, sample_limit=0)
    selector = RetrievedSchemaSelector(
        FakeRetriever(
            (
                _match("orders", column_name="order_date"),
                _match("missing", column_name="stale"),
            )
        )
    )

    selected = selector.select_schema(schema, "Recent orders?")

    assert [table.name for table in selected.tables] == ["orders"]
    assert [column.name for column in selected.tables[0].columns] == ["order_date"]


def test_retrieved_schema_selector_rejects_no_live_matches() -> None:
    selector = RetrievedSchemaSelector(FakeRetriever((_match("missing"),)))

    with pytest.raises(ValueError, match="did not select"):
        selector.select_schema(DatabaseSchema(tables=()), "Question?")
