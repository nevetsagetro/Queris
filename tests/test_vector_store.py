from pathlib import Path

import duckdb
import pytest

from queris.schema_embeddings import SchemaDocument, SchemaEmbedding
from queris.vector_store import VectorStoreError, replace_schema_embeddings


def _embedding(
    table_name: str,
    vector: tuple[float, ...],
    *,
    column_name: str | None = None,
) -> SchemaEmbedding:
    kind = "column" if column_name else "table"
    document = SchemaDocument(
        kind=kind,
        schema_name="main",
        table_name=table_name,
        column_name=column_name,
        text=f'{{"table_name":"{table_name}"}}',
    )
    return SchemaEmbedding(document=document, vector=vector)


def test_replace_schema_embeddings_uses_fixed_dimension_and_replaces_rows(
    tmp_path: Path,
) -> None:
    database = tmp_path / "vectors.duckdb"
    replace_schema_embeddings(
        database,
        (_embedding("orders", (1.0, 0.0)), _embedding("regions", (0.0, 1.0))),
        model="test-model",
        create_hnsw=False,
    )

    replace_schema_embeddings(
        database,
        (_embedding("products", (0.5, 0.5)),),
        model="replacement-model",
        create_hnsw=False,
    )

    connection = duckdb.connect(str(database), read_only=True)
    try:
        rows = connection.execute(
            """
            SELECT table_name, embedding_model, embedding
            FROM queris.schema_embeddings
            """
        ).fetchall()
        column_type = connection.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = 'queris'
              AND table_name = 'schema_embeddings'
              AND column_name = 'embedding'
            """
        ).fetchone()
    finally:
        connection.close()

    assert rows == [("products", "replacement-model", (0.5, 0.5))]
    assert column_type == ("FLOAT[2]",)


def test_replace_schema_embeddings_creates_persisted_cosine_hnsw(
    tmp_path: Path,
) -> None:
    probe = duckdb.connect()
    installed = probe.execute(
        "SELECT installed FROM duckdb_extensions() WHERE extension_name = 'vss'"
    ).fetchone()
    probe.close()
    if installed != (True,):
        pytest.skip("DuckDB vss extension is not installed")

    database = tmp_path / "vectors.duckdb"
    replace_schema_embeddings(
        database,
        (_embedding("orders", (1.0, 0.0)),),
        model="test-model",
    )

    connection = duckdb.connect(str(database))
    try:
        connection.execute("LOAD vss")
        index = connection.execute(
            """
            SELECT index_name, sql
            FROM duckdb_indexes()
            WHERE schema_name = 'queris'
            """
        ).fetchone()
        plan = connection.execute(
            """
            EXPLAIN SELECT *
            FROM queris.schema_embeddings
            ORDER BY array_cosine_distance(embedding, [1.0, 0.0]::FLOAT[2])
            LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()

    assert index is not None
    assert index[0] == "queris_schema_embeddings_hnsw"
    assert plan is not None
    assert "HNSW_INDEX_SCAN" in plan[1]


@pytest.mark.parametrize(
    ("embeddings", "error"),
    [
        ((), "at least one"),
        (
            (_embedding("orders", (1.0,)), _embedding("regions", (1.0, 0.0))),
            "consistent dimension",
        ),
        (
            (_embedding("orders", (1.0,)), _embedding("orders", (0.0,))),
            "duplicate document",
        ),
    ],
)
def test_replace_schema_embeddings_rejects_invalid_batches_before_writing(
    tmp_path: Path,
    embeddings: tuple[SchemaEmbedding, ...],
    error: str,
) -> None:
    database = tmp_path / "vectors.duckdb"

    with pytest.raises(VectorStoreError, match=error):
        replace_schema_embeddings(
            database,
            embeddings,
            model="test-model",
            create_hnsw=False,
        )

    assert not database.exists()


def test_replace_schema_embeddings_rejects_empty_model_before_writing(
    tmp_path: Path,
) -> None:
    database = tmp_path / "vectors.duckdb"

    with pytest.raises(ValueError, match="model"):
        replace_schema_embeddings(
            database,
            (_embedding("orders", (1.0,)),),
            model=" ",
            create_hnsw=False,
        )

    assert not database.exists()


def test_rejected_replacement_preserves_existing_store(tmp_path: Path) -> None:
    database = tmp_path / "vectors.duckdb"
    replace_schema_embeddings(
        database,
        (_embedding("orders", (1.0, 0.0)),),
        model="original-model",
        create_hnsw=False,
    )

    with pytest.raises(VectorStoreError, match="consistent dimension"):
        replace_schema_embeddings(
            database,
            (_embedding("orders", (1.0,)), _embedding("regions", (1.0, 0.0))),
            model="replacement-model",
            create_hnsw=False,
        )

    connection = duckdb.connect(str(database), read_only=True)
    try:
        stored = connection.execute(
            "SELECT table_name, embedding_model FROM queris.schema_embeddings"
        ).fetchall()
    finally:
        connection.close()
    assert stored == [("orders", "original-model")]
