"""Read-only cosine retrieval over stored schema embeddings."""

import math
from pathlib import Path
from typing import Literal, Protocol

import duckdb
from pydantic import BaseModel, ConfigDict

from queris.vector_store import VECTOR_SCHEMA, VECTOR_TABLE

MAX_TOP_K = 100


class QueryEmbeddingProvider(Protocol):
    """Embed a question with a named, store-compatible model."""

    model: str

    def embed_query(self, text: str) -> tuple[float, ...]: ...


class SchemaRetrievalError(RuntimeError):
    """Raised when schema retrieval cannot safely query the vector store."""


class SchemaMatch(BaseModel):
    """One ordered schema retrieval result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["table", "column"]
    schema_name: str
    table_name: str
    column_name: str | None = None
    document_text: str
    similarity: float


def retrieve_schema(
    database_path: str | Path,
    question: str,
    provider: QueryEmbeddingProvider,
    *,
    top_k: int = 5,
    load_vss: bool = True,
) -> tuple[SchemaMatch, ...]:
    """Embed one question and return its most similar schema documents."""
    if not isinstance(question, str):
        raise TypeError("question must be a string")
    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("question must be a non-empty string")
    _validate_top_k(top_k)
    if not isinstance(provider.model, str) or not provider.model.strip():
        raise ValueError("model must be a non-empty string")
    return retrieve_schema_matches(
        database_path,
        provider.embed_query(normalized_question),
        model=provider.model,
        top_k=top_k,
        load_vss=load_vss,
    )


def retrieve_schema_matches(
    database_path: str | Path,
    query_vector: tuple[float, ...],
    *,
    model: str,
    top_k: int = 5,
    load_vss: bool = True,
) -> tuple[SchemaMatch, ...]:
    """Return exact cosine top-k matches for one validated query vector."""
    _validate_top_k(top_k)
    normalized_model = model.strip()
    if not normalized_model:
        raise ValueError("model must be a non-empty string")
    _validate_query_vector(query_vector)

    path = Path(database_path)
    if not path.is_file():
        raise FileNotFoundError(f"Vector database does not exist: {path}")

    connection = duckdb.connect(database=str(path), read_only=True)
    try:
        if load_vss:
            try:
                connection.execute("LOAD vss")
            except duckdb.Error as error:
                raise SchemaRetrievalError("DuckDB vss is required to read this index") from error
        dimension, stored_model = _read_store_contract(connection)
        if len(query_vector) != dimension:
            raise SchemaRetrievalError(
                f"query vector dimension {len(query_vector)} does not match stored {dimension}"
            )
        if normalized_model != stored_model:
            raise SchemaRetrievalError(
                f"query model {normalized_model!r} does not match stored {stored_model!r}"
            )
        return _query_matches(connection, query_vector, dimension=dimension, top_k=top_k)
    finally:
        connection.close()


def _read_store_contract(connection: duckdb.DuckDBPyConnection) -> tuple[int, str]:
    try:
        rows = connection.execute(
            f"""
            SELECT DISTINCT array_length(embedding), embedding_model
            FROM {VECTOR_SCHEMA}.{VECTOR_TABLE}
            """
        ).fetchall()
    except duckdb.Error as error:
        raise SchemaRetrievalError("vector database has no valid schema embedding store") from error
    if len(rows) != 1:
        raise SchemaRetrievalError("vector store must contain one dimension and embedding model")
    dimension, model = rows[0]
    return int(dimension), str(model)


def _query_matches(
    connection: duckdb.DuckDBPyConnection,
    query_vector: tuple[float, ...],
    *,
    dimension: int,
    top_k: int,
) -> tuple[SchemaMatch, ...]:
    rows = connection.execute(
        f"""
        SELECT
            kind,
            schema_name,
            table_name,
            column_name,
            document_text,
            1.0 - array_cosine_distance(embedding, ?::FLOAT[{dimension}]) AS similarity
        FROM {VECTOR_SCHEMA}.{VECTOR_TABLE}
        ORDER BY similarity DESC, document_key ASC
        LIMIT ?
        """,
        [list(query_vector), top_k],
    ).fetchall()
    return tuple(
        SchemaMatch(
            kind=kind,
            schema_name=schema_name,
            table_name=table_name,
            column_name=column_name,
            document_text=document_text,
            similarity=similarity,
        )
        for kind, schema_name, table_name, column_name, document_text, similarity in rows
    )


def _validate_top_k(top_k: int) -> None:
    if type(top_k) is not int or not 1 <= top_k <= MAX_TOP_K:
        raise ValueError(f"top_k must be an integer between 1 and {MAX_TOP_K}")


def _validate_query_vector(vector: tuple[float, ...]) -> None:
    if not vector:
        raise ValueError("query vector must not be empty")
    if not all(math.isfinite(value) for value in vector):
        raise ValueError("query vector must contain only finite values")
    if not any(value != 0.0 for value in vector):
        raise ValueError("query vector must not be a zero vector")
