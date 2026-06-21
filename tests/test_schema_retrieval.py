import math
from pathlib import Path

import duckdb
import pytest

from queris.schema_embeddings import SchemaDocument, SchemaEmbedding
from queris.schema_retrieval import (
    MAX_TOP_K,
    SchemaRetrievalError,
    retrieve_schema,
    retrieve_schema_matches,
)
from queris.vector_store import replace_schema_embeddings


def _embedding(
    table_name: str,
    vector: tuple[float, ...],
    *,
    column_name: str | None = None,
) -> SchemaEmbedding:
    kind = "column" if column_name else "table"
    return SchemaEmbedding(
        document=SchemaDocument(
            kind=kind,
            schema_name="main",
            table_name=table_name,
            column_name=column_name,
            text=f'{{"table_name":"{table_name}","column_name":{column_name!r}}}',
        ),
        vector=vector,
    )


@pytest.fixture
def vector_database(tmp_path: Path) -> Path:
    path = tmp_path / "vectors.duckdb"
    replace_schema_embeddings(
        path,
        (
            _embedding("regions", (0.0, 1.0)),
            _embedding("orders", (1.0, 0.0)),
            _embedding("orders", (0.8, 0.2), column_name="order_date"),
        ),
        model="test-model",
        create_hnsw=False,
    )
    return path


def test_retrieve_schema_matches_returns_ordered_cosine_top_k(
    vector_database: Path,
) -> None:
    matches = retrieve_schema_matches(
        vector_database,
        (1.0, 0.0),
        model="test-model",
        top_k=2,
        load_vss=False,
    )

    assert [(match.table_name, match.column_name) for match in matches] == [
        ("orders", None),
        ("orders", "order_date"),
    ]
    assert matches[0].similarity == pytest.approx(1.0)
    assert matches[1].similarity < matches[0].similarity


def test_retrieve_schema_matches_orders_ties_by_document_key(tmp_path: Path) -> None:
    path = tmp_path / "vectors.duckdb"
    replace_schema_embeddings(
        path,
        (_embedding("beta", (1.0, 0.0)), _embedding("alpha", (1.0, 0.0))),
        model="test-model",
        create_hnsw=False,
    )

    matches = retrieve_schema_matches(
        path,
        (1.0, 0.0),
        model="test-model",
        top_k=2,
        load_vss=False,
    )

    assert [match.table_name for match in matches] == ["alpha", "beta"]


class FakeQueryProvider:
    model = "test-model"

    def __init__(self) -> None:
        self.questions: list[str] = []

    def embed_query(self, text: str) -> tuple[float, ...]:
        self.questions.append(text)
        return (1.0, 0.0)


def test_retrieve_schema_embeds_normalized_question(vector_database: Path) -> None:
    provider = FakeQueryProvider()

    matches = retrieve_schema(
        vector_database,
        "  Which orders were recent?  ",
        provider,
        top_k=1,
        load_vss=False,
    )

    assert provider.questions == ["Which orders were recent?"]
    assert matches[0].table_name == "orders"


@pytest.mark.parametrize("top_k", [0, MAX_TOP_K + 1, 1.5, True])
def test_retrieve_schema_matches_rejects_invalid_top_k(
    vector_database: Path,
    top_k: object,
) -> None:
    with pytest.raises(ValueError, match="top_k"):
        retrieve_schema_matches(
            vector_database,
            (1.0, 0.0),
            model="test-model",
            top_k=top_k,  # type: ignore[arg-type]
            load_vss=False,
        )


@pytest.mark.parametrize("vector", [(), (1.0,), (0.0, 0.0), (math.nan, 0.0)])
def test_retrieve_schema_matches_rejects_incompatible_query_vectors(
    vector_database: Path,
    vector: tuple[float, ...],
) -> None:
    error = "dimension" if vector == (1.0,) else "query vector"
    with pytest.raises((ValueError, SchemaRetrievalError), match=error):
        retrieve_schema_matches(
            vector_database,
            vector,
            model="test-model",
            load_vss=False,
        )


def test_retrieve_schema_matches_rejects_model_mismatch(vector_database: Path) -> None:
    with pytest.raises(SchemaRetrievalError, match="does not match"):
        retrieve_schema_matches(
            vector_database,
            (1.0, 0.0),
            model="different-model",
            load_vss=False,
        )


def test_retrieve_schema_matches_rejects_mixed_store_contract(
    vector_database: Path,
) -> None:
    connection = duckdb.connect(str(vector_database))
    connection.execute(
        "UPDATE queris.schema_embeddings SET embedding_model = 'other' WHERE table_name = 'regions'"
    )
    connection.close()

    with pytest.raises(SchemaRetrievalError, match="one dimension and embedding model"):
        retrieve_schema_matches(
            vector_database,
            (1.0, 0.0),
            model="test-model",
            load_vss=False,
        )


@pytest.mark.parametrize("question", ["", "   "])
def test_retrieve_schema_rejects_empty_question(
    vector_database: Path,
    question: str,
) -> None:
    with pytest.raises(ValueError, match="question"):
        retrieve_schema(
            vector_database,
            question,
            FakeQueryProvider(),
            load_vss=False,
        )


def test_retrieve_schema_rejects_top_k_before_embedding(vector_database: Path) -> None:
    provider = FakeQueryProvider()

    with pytest.raises(ValueError, match="top_k"):
        retrieve_schema(
            vector_database,
            "Which orders were recent?",
            provider,
            top_k=0,
            load_vss=False,
        )

    assert provider.questions == []


def test_retrieve_schema_matches_requires_existing_database(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="does not exist"):
        retrieve_schema_matches(
            tmp_path / "missing.duckdb",
            (1.0, 0.0),
            model="test-model",
            load_vss=False,
        )
