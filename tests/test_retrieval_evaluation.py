from pathlib import Path

import pytest

from queris.database import read_only_connection
from queris.retrieval_evaluation import compare_schema_retrieval, evaluate_schema_retrieval
from queris.schema import introspect_schema
from queris.schema_embeddings import DeterministicEmbeddingProvider, SchemaEmbeddingError
from queris.schema_enrichment import load_schema_enrichment, merge_schema_enrichment
from queris.wide_schema import create_wide_schema_database, load_retrieval_labels

LABELS_PATH = Path("evals/wide_schema_retrieval.json")
ENRICHMENT_PATH = Path("metadata/wide-schema.v1.yaml")


def test_deterministic_embedding_provider_is_repeatable_and_token_based() -> None:
    first = DeterministicEmbeddingProvider(dimensions=64)
    second = DeterministicEmbeddingProvider(dimensions=64)

    assert first.embed(("Invoice balance",)) == second.embed(("Invoice balance",))
    assert first.embed_query("invoice balance") == first.embed_query("balance invoice invoice")
    assert first.embed_query("invoice balance") != first.embed_query("inventory units")


@pytest.mark.parametrize("dimensions", [0, -1, 1.5, True])
def test_deterministic_embedding_provider_rejects_invalid_dimensions(
    dimensions: object,
) -> None:
    with pytest.raises(ValueError, match="dimensions"):
        DeterministicEmbeddingProvider(dimensions=dimensions)  # type: ignore[arg-type]


def test_deterministic_embedding_provider_rejects_tokenless_text() -> None:
    with pytest.raises(SchemaEmbeddingError, match="token"):
        DeterministicEmbeddingProvider().embed_query("---")


def test_enrichment_improves_wide_schema_retrieval_at_five(tmp_path: Path) -> None:
    database = create_wide_schema_database(tmp_path / "wide.duckdb")
    with read_only_connection(database) as connection:
        raw_schema = introspect_schema(connection, sample_limit=0)
    enriched_schema = merge_schema_enrichment(
        raw_schema,
        load_schema_enrichment(ENRICHMENT_PATH),
    )

    comparison = compare_schema_retrieval(
        raw_schema,
        enriched_schema,
        load_retrieval_labels(LABELS_PATH),
        DeterministicEmbeddingProvider(),
        top_k=5,
    )

    assert comparison.raw.precision == pytest.approx(0.14)
    assert comparison.raw.recall == pytest.approx(0.70)
    assert comparison.enriched.precision == pytest.approx(0.20)
    assert comparison.enriched.recall == pytest.approx(1.0)
    assert comparison.precision_improvement == pytest.approx(0.06)
    assert comparison.recall_improvement == pytest.approx(0.30)


@pytest.mark.parametrize("top_k", [0, 1.5, True])
def test_evaluate_schema_retrieval_rejects_invalid_top_k(
    tmp_path: Path,
    top_k: object,
) -> None:
    database = create_wide_schema_database(tmp_path / "wide.duckdb")
    with read_only_connection(database) as connection:
        schema = introspect_schema(connection, sample_limit=0)

    with pytest.raises(ValueError, match="top_k"):
        evaluate_schema_retrieval(
            schema,
            load_retrieval_labels(LABELS_PATH),
            DeterministicEmbeddingProvider(),
            top_k=top_k,  # type: ignore[arg-type]
        )
