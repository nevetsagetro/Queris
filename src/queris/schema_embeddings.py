"""Deterministic schema documents and embedding-provider boundary."""

import json
import math
import os
from typing import Any, Literal, Protocol

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, field_validator

from queris.schema import ColumnSchema, DatabaseSchema, TableSchema

DEFAULT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
MAX_SAMPLE_TEXT_LENGTH = 100


class SchemaDocument(BaseModel):
    """Stable text representation of one table or column."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["table", "column"]
    schema_name: str
    table_name: str
    column_name: str | None = None
    text: str


class SchemaEmbedding(BaseModel):
    """One schema document paired with its numeric embedding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document: SchemaDocument
    vector: tuple[float, ...]

    @field_validator("vector")
    @classmethod
    def require_finite_vector(cls, vector: tuple[float, ...]) -> tuple[float, ...]:
        if not vector:
            raise ValueError("embedding vector must not be empty")
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("embedding vector must contain only finite values")
        return vector


class EmbeddingProvider(Protocol):
    """Provider-neutral batch embedding boundary."""

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class SchemaEmbeddingError(RuntimeError):
    """Raised when an embedding provider returns an unusable response."""


class _ContentEmbedding(Protocol):
    values: list[float] | None


class _EmbedResponse(Protocol):
    embeddings: list[_ContentEmbedding] | None


class _ModelsAPI(Protocol):
    def embed_content(
        self,
        *,
        model: str,
        contents: list[str],
        config: types.EmbedContentConfig,
    ) -> _EmbedResponse: ...


class _GeminiClient(Protocol):
    models: _ModelsAPI


def build_schema_documents(schema: DatabaseSchema) -> tuple[SchemaDocument, ...]:
    """Build ordered embedding documents from live, optionally enriched schema."""
    documents: list[SchemaDocument] = []
    for table in schema.tables:
        documents.append(_table_document(table))
        documents.extend(_column_document(table, column) for column in table.columns)
    return tuple(documents)


def embed_schema(
    schema: DatabaseSchema,
    provider: EmbeddingProvider,
) -> tuple[SchemaEmbedding, ...]:
    """Embed every table and column document with one provider batch."""
    documents = build_schema_documents(schema)
    if not documents:
        return ()

    vectors = provider.embed(tuple(document.text for document in documents))
    if len(vectors) != len(documents):
        raise SchemaEmbeddingError("embedding provider returned an unexpected vector count")
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1:
        raise SchemaEmbeddingError("embedding provider returned inconsistent dimensions")

    try:
        return tuple(
            SchemaEmbedding(document=document, vector=vector)
            for document, vector in zip(documents, vectors, strict=True)
        )
    except ValueError as error:
        raise SchemaEmbeddingError("embedding provider returned an invalid vector") from error


class GeminiEmbeddingProvider:
    """Generate retrieval-document embeddings through the Gemini API."""

    def __init__(
        self,
        *,
        model: str | None = None,
        client: _GeminiClient | None = None,
    ) -> None:
        selected_model = (
            model
            if model is not None
            else os.getenv("GEMINI_EMBEDDING_MODEL", DEFAULT_GEMINI_EMBEDDING_MODEL)
        )
        if not selected_model.strip():
            raise ValueError("model must be a non-empty string")
        self.model = selected_model
        self._client = client or self._create_client()

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        """Embed one non-empty batch in input order."""
        if not texts:
            return ()
        response = self._client.models.embed_content(
            model=self.model,
            contents=list(texts),
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        embeddings = response.embeddings or []
        return tuple(tuple(embedding.values or ()) for embedding in embeddings)

    @staticmethod
    def _create_client() -> genai.Client:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise SchemaEmbeddingError("GEMINI_API_KEY is required for live schema embeddings")
        return genai.Client(api_key=api_key)


def _table_document(table: TableSchema) -> SchemaDocument:
    payload = {
        "aliases": list(table.aliases),
        "business_terms": list(table.business_terms),
        "description": table.description,
        "kind": "table",
        "schema_name": table.schema_name,
        "table_name": table.name,
    }
    return SchemaDocument(
        kind="table",
        schema_name=table.schema_name,
        table_name=table.name,
        text=_dump_payload(payload),
    )


def _column_document(table: TableSchema, column: ColumnSchema) -> SchemaDocument:
    payload = {
        "aliases": list(column.aliases),
        "business_terms": list(column.business_terms),
        "column_name": column.name,
        "data_type": column.data_type,
        "description": column.description,
        "kind": "column",
        "nullable": column.nullable,
        "sample_values": [_safe_sample(value) for value in column.sample_values],
        "schema_name": table.schema_name,
        "table_name": table.name,
        "unit": column.unit,
    }
    return SchemaDocument(
        kind="column",
        schema_name=table.schema_name,
        table_name=table.name,
        column_name=column.name,
        text=_dump_payload(payload),
    )


def _safe_sample(value: Any) -> str:
    rendered = str(value)
    if len(rendered) <= MAX_SAMPLE_TEXT_LENGTH:
        return rendered
    return f"{rendered[:MAX_SAMPLE_TEXT_LENGTH]}..."


def _dump_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
