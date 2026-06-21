"""Trusted setup writes for the rebuildable DuckDB schema-vector index."""

import json
from pathlib import Path

import duckdb

from queris.schema_embeddings import SchemaEmbedding

VECTOR_SCHEMA = "queris"
VECTOR_TABLE = "schema_embeddings"
VECTOR_INDEX = "queris_schema_embeddings_hnsw"


class VectorStoreError(RuntimeError):
    """Raised when schema embeddings cannot be stored safely."""


def replace_schema_embeddings(
    database_path: str | Path,
    embeddings: tuple[SchemaEmbedding, ...],
    *,
    model: str,
    create_hnsw: bool = True,
    install_vss: bool = False,
) -> None:
    """Atomically replace all schema embeddings in a dedicated DuckDB index."""
    normalized_model = model.strip()
    if not normalized_model:
        raise ValueError("model must be a non-empty string")
    dimension, rows = _prepare_rows(embeddings, normalized_model)

    path = Path(database_path)
    existed = path.exists()
    connection = duckdb.connect(database=str(path))
    try:
        if create_hnsw:
            _load_vss(connection, install=install_vss)
        _replace_rows(
            connection,
            dimension=dimension,
            rows=rows,
            create_hnsw=create_hnsw,
        )
    except Exception:
        connection.close()
        if not existed:
            path.unlink(missing_ok=True)
        raise
    else:
        connection.close()


def _prepare_rows(
    embeddings: tuple[SchemaEmbedding, ...],
    model: str,
) -> tuple[int, list[tuple[object, ...]]]:
    if not embeddings:
        raise VectorStoreError("at least one schema embedding is required")

    dimensions = {len(embedding.vector) for embedding in embeddings}
    if len(dimensions) != 1:
        raise VectorStoreError("schema embeddings must have one consistent dimension")
    dimension = dimensions.pop()

    rows = [
        (
            _document_key(embedding),
            embedding.document.kind,
            embedding.document.schema_name,
            embedding.document.table_name,
            embedding.document.column_name,
            embedding.document.text,
            model,
            list(embedding.vector),
        )
        for embedding in embeddings
    ]
    keys = [str(row[0]) for row in rows]
    if len(keys) != len(set(keys)):
        raise VectorStoreError("schema embeddings contain duplicate document references")
    return dimension, rows


def _replace_rows(
    connection: duckdb.DuckDBPyConnection,
    *,
    dimension: int,
    rows: list[tuple[object, ...]],
    create_hnsw: bool,
) -> None:
    connection.execute("BEGIN")
    try:
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {VECTOR_SCHEMA}")
        connection.execute(f"DROP TABLE IF EXISTS {VECTOR_SCHEMA}.{VECTOR_TABLE}")
        connection.execute(
            f"""
            CREATE TABLE {VECTOR_SCHEMA}.{VECTOR_TABLE} (
                document_key VARCHAR PRIMARY KEY,
                kind VARCHAR NOT NULL CHECK (kind IN ('table', 'column')),
                schema_name VARCHAR NOT NULL,
                table_name VARCHAR NOT NULL,
                column_name VARCHAR,
                document_text VARCHAR NOT NULL,
                embedding_model VARCHAR NOT NULL,
                embedding FLOAT[{dimension}] NOT NULL
            )
            """
        )
        connection.executemany(
            f"""
            INSERT INTO {VECTOR_SCHEMA}.{VECTOR_TABLE}
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        if create_hnsw:
            connection.execute(
                f"""
                CREATE INDEX {VECTOR_INDEX}
                ON {VECTOR_SCHEMA}.{VECTOR_TABLE}
                USING HNSW (embedding)
                WITH (metric = 'cosine')
                """
            )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def _load_vss(connection: duckdb.DuckDBPyConnection, *, install: bool) -> None:
    if install:
        connection.execute("INSTALL vss")
    try:
        connection.execute("LOAD vss")
    except duckdb.Error as error:
        raise VectorStoreError(
            "DuckDB vss is not installed; run trusted setup with install_vss=True"
        ) from error
    connection.execute("SET hnsw_enable_experimental_persistence = true")


def _document_key(embedding: SchemaEmbedding) -> str:
    document = embedding.document
    return json.dumps(
        [document.kind, document.schema_name, document.table_name, document.column_name],
        ensure_ascii=True,
        separators=(",", ":"),
    )
