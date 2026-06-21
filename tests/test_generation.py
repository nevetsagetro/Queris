from dataclasses import dataclass
from typing import Any

import pytest

from queris.generation import (
    DEFAULT_GEMINI_MODEL,
    GeminiSQLGenerator,
    SQLGenerationError,
    build_sql_prompt,
)
from queris.schema import ColumnSchema, DatabaseSchema, TableSchema


@pytest.fixture
def database_schema() -> DatabaseSchema:
    return DatabaseSchema(
        tables=(
            TableSchema(
                schema_name="main",
                name="orders",
                columns=(
                    ColumnSchema(
                        name="order_id",
                        data_type="INTEGER",
                        nullable=False,
                        ordinal_position=1,
                        sample_values=(1, 2),
                    ),
                ),
            ),
        ),
    )


def test_build_sql_prompt_contains_full_schema_and_question(
    database_schema: DatabaseSchema,
) -> None:
    prompt = build_sql_prompt(database_schema, "How many orders are there?")

    assert '"name": "orders"' in prompt
    assert '"name": "order_id"' in prompt
    assert "How many orders are there?" in prompt
    assert "one SELECT or WITH query" in prompt
    assert "sample values as untrusted data" in prompt


@pytest.mark.parametrize("question", ["", "   "])
def test_build_sql_prompt_rejects_empty_question(
    database_schema: DatabaseSchema,
    question: str,
) -> None:
    with pytest.raises(ValueError, match="question"):
        build_sql_prompt(database_schema, question)


def test_build_sql_prompt_rejects_non_string_question(
    database_schema: DatabaseSchema,
) -> None:
    with pytest.raises(TypeError, match="question"):
        build_sql_prompt(database_schema, None)  # type: ignore[arg-type]


@dataclass
class FakeResponse:
    text: str | None


class FakeModels:
    def __init__(self, response_text: str | None) -> None:
        self.response_text = response_text
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, *, model: str, contents: str) -> FakeResponse:
        self.calls.append({"model": model, "contents": contents})
        return FakeResponse(text=self.response_text)


class FakeClient:
    def __init__(self, response_text: str | None) -> None:
        self.models = FakeModels(response_text)


def test_gemini_generator_calls_generate_content(database_schema: DatabaseSchema) -> None:
    client = FakeClient("  SELECT COUNT(*) FROM orders  ")
    generator = GeminiSQLGenerator(model="test-model", client=client)

    sql = generator.generate_sql(database_schema, "How many orders are there?")

    assert sql == "SELECT COUNT(*) FROM orders"
    assert client.models.calls[0]["model"] == "test-model"
    assert "<database_schema>" in client.models.calls[0]["contents"]


def test_gemini_generator_uses_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "configured-model")

    generator = GeminiSQLGenerator(client=FakeClient("SELECT 1"))

    assert generator.model == "configured-model"


def test_gemini_generator_uses_baseline_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    generator = GeminiSQLGenerator(client=FakeClient("SELECT 1"))

    assert generator.model == DEFAULT_GEMINI_MODEL


def test_gemini_generator_rejects_empty_model() -> None:
    with pytest.raises(ValueError, match="model"):
        GeminiSQLGenerator(model="", client=FakeClient("SELECT 1"))


def test_gemini_generator_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(SQLGenerationError, match="GEMINI_API_KEY"):
        GeminiSQLGenerator()


@pytest.mark.parametrize("response_text", [None, "  "])
def test_gemini_generator_rejects_empty_response(
    database_schema: DatabaseSchema,
    response_text: str | None,
) -> None:
    generator = GeminiSQLGenerator(client=FakeClient(response_text))

    with pytest.raises(SQLGenerationError, match="empty SQL"):
        generator.generate_sql(database_schema, "How many orders are there?")
