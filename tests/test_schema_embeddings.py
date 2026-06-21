import json
import math
from dataclasses import dataclass
from typing import Any

import pytest

from queris.schema import ColumnSchema, DatabaseSchema, TableSchema
from queris.schema_embeddings import (
    DEFAULT_GEMINI_EMBEDDING_MODEL,
    MAX_SAMPLE_TEXT_LENGTH,
    GeminiEmbeddingProvider,
    SchemaEmbeddingError,
    build_schema_documents,
    embed_schema,
)


def _schema() -> DatabaseSchema:
    return DatabaseSchema(
        tables=(
            TableSchema(
                schema_name="main",
                name="order_items",
                description="Financial measures for order lines.",
                business_terms=("sales line",),
                aliases=("line items",),
                columns=(
                    ColumnSchema(
                        name="revenue",
                        data_type="DECIMAL(12,2)",
                        nullable=False,
                        ordinal_position=1,
                        sample_values=("40.00", "x" * (MAX_SAMPLE_TEXT_LENGTH + 20)),
                        description="Sales revenue.",
                        business_terms=("sales",),
                        aliases=("line revenue",),
                        unit="USD",
                    ),
                ),
            ),
        )
    )


def test_build_schema_documents_covers_identifiers_metadata_and_bounded_samples() -> None:
    table_document, column_document = build_schema_documents(_schema())

    table = json.loads(table_document.text)
    column = json.loads(column_document.text)
    assert table == {
        "aliases": ["line items"],
        "business_terms": ["sales line"],
        "description": "Financial measures for order lines.",
        "kind": "table",
        "schema_name": "main",
        "table_name": "order_items",
    }
    assert column["column_name"] == "revenue"
    assert column["data_type"] == "DECIMAL(12,2)"
    assert column["description"] == "Sales revenue."
    assert column["business_terms"] == ["sales"]
    assert column["aliases"] == ["line revenue"]
    assert column["unit"] == "USD"
    assert column["sample_values"][0] == "40.00"
    assert column["sample_values"][1] == f"{'x' * MAX_SAMPLE_TEXT_LENGTH}..."


class FakeProvider:
    def __init__(self, vectors: tuple[tuple[float, ...], ...]) -> None:
        self.vectors = vectors
        self.calls: list[tuple[str, ...]] = []

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.calls.append(texts)
        return self.vectors


def test_embed_schema_batches_documents_and_preserves_order() -> None:
    provider = FakeProvider(((1.0, 0.0), (0.0, 1.0)))

    embeddings = embed_schema(_schema(), provider)

    assert len(provider.calls) == 1
    assert [embedding.document.kind for embedding in embeddings] == ["table", "column"]
    assert [embedding.vector for embedding in embeddings] == [(1.0, 0.0), (0.0, 1.0)]


@pytest.mark.parametrize(
    ("vectors", "error"),
    [
        (((1.0,),), "vector count"),
        (((1.0,), (1.0, 2.0)), "inconsistent dimensions"),
        (((), ()), "invalid vector"),
        (((math.nan,), (1.0,)), "invalid vector"),
        (((0.0, 0.0), (1.0, 0.0)), "invalid vector"),
    ],
)
def test_embed_schema_rejects_invalid_provider_responses(
    vectors: tuple[tuple[float, ...], ...],
    error: str,
) -> None:
    with pytest.raises(SchemaEmbeddingError, match=error):
        embed_schema(_schema(), FakeProvider(vectors))


@dataclass
class FakeContentEmbedding:
    values: list[float] | None


@dataclass
class FakeEmbedResponse:
    embeddings: list[FakeContentEmbedding] | None


class FakeModels:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def embed_content(self, **kwargs: Any) -> FakeEmbedResponse:
        self.calls.append(kwargs)
        return FakeEmbedResponse(
            embeddings=[FakeContentEmbedding([1.0, 2.0]) for _ in kwargs["contents"]]
        )


class FakeClient:
    def __init__(self) -> None:
        self.models = FakeModels()


def test_gemini_embedding_provider_uses_retrieval_document_batch() -> None:
    client = FakeClient()
    provider = GeminiEmbeddingProvider(model="test-embedding-model", client=client)

    vectors = provider.embed(("first", "second"))

    assert vectors == ((1.0, 2.0), (1.0, 2.0))
    call = client.models.calls[0]
    assert call["model"] == "test-embedding-model"
    assert call["contents"] == ["first", "second"]
    assert call["config"].task_type == "RETRIEVAL_DOCUMENT"


def test_gemini_embedding_provider_uses_retrieval_query_task() -> None:
    client = FakeClient()
    provider = GeminiEmbeddingProvider(model="test-embedding-model", client=client)

    vector = provider.embed_query("Which orders had the most revenue?")

    assert vector == (1.0, 2.0)
    call = client.models.calls[0]
    assert call["contents"] == ["Which orders had the most revenue?"]
    assert call["config"].task_type == "RETRIEVAL_QUERY"


def test_gemini_embedding_provider_uses_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_EMBEDDING_MODEL", "configured-embedding-model")

    provider = GeminiEmbeddingProvider(client=FakeClient())

    assert provider.model == "configured-embedding-model"


def test_gemini_embedding_provider_uses_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_EMBEDDING_MODEL", raising=False)

    provider = GeminiEmbeddingProvider(client=FakeClient())

    assert provider.model == DEFAULT_GEMINI_EMBEDDING_MODEL


def test_gemini_embedding_provider_rejects_empty_model() -> None:
    with pytest.raises(ValueError, match="model"):
        GeminiEmbeddingProvider(model="", client=FakeClient())


def test_gemini_embedding_provider_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(SchemaEmbeddingError, match="GEMINI_API_KEY"):
        GeminiEmbeddingProvider()
