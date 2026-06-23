"""Offline precision/recall evaluation for schema retrieval."""

import argparse
import math
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from queris.database import read_only_connection
from queris.schema import DatabaseSchema, introspect_schema
from queris.schema_embeddings import (
    DeterministicEmbeddingProvider,
    SchemaDocument,
    SchemaEmbedding,
    embed_schema,
)
from queris.schema_enrichment import load_schema_enrichment, merge_schema_enrichment
from queris.wide_schema import ColumnReference, RetrievalLabelSet, load_retrieval_labels


class EvaluationEmbeddingProvider(Protocol):
    """Embedding operations required by the offline evaluator."""

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...

    def embed_query(self, text: str) -> tuple[float, ...]: ...


class RetrievalCaseMetrics(BaseModel):
    """Precision and recall for one labeled question."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    precision: float
    recall: float
    relevant_retrieved: int


class RetrievalMetrics(BaseModel):
    """Macro retrieval metrics at one fixed rank cutoff."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    top_k: int
    precision: float
    recall: float
    cases: tuple[RetrievalCaseMetrics, ...]


class RetrievalComparison(BaseModel):
    """Raw and enriched retrieval metrics over the same labels."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw: RetrievalMetrics
    enriched: RetrievalMetrics

    @property
    def precision_improvement(self) -> float:
        """Return enriched minus raw macro precision."""
        return self.enriched.precision - self.raw.precision

    @property
    def recall_improvement(self) -> float:
        """Return enriched minus raw macro recall."""
        return self.enriched.recall - self.raw.recall


def rank_schema_documents(
    schema: DatabaseSchema,
    question: str,
    provider: EvaluationEmbeddingProvider,
    *,
    top_k: int = 5,
) -> tuple[SchemaDocument, ...]:
    """Return deterministic top-k schema documents for one question."""
    if not isinstance(question, str):
        raise TypeError("question must be a string")
    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("question must be a non-empty string")
    if type(top_k) is not int or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    embeddings = embed_schema(schema, provider)
    if not embeddings:
        raise ValueError("schema must contain at least one document")
    ranked = _rank_schema_embeddings(
        embeddings,
        provider.embed_query(normalized_question),
        top_k=top_k,
    )
    return tuple(embedding.document for embedding in ranked)


def evaluate_schema_retrieval(
    schema: DatabaseSchema,
    labels: RetrievalLabelSet,
    provider: EvaluationEmbeddingProvider,
    *,
    top_k: int = 5,
) -> RetrievalMetrics:
    """Measure macro precision and recall against labeled relevant columns."""
    if type(top_k) is not int or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    embeddings = embed_schema(schema, provider)
    if not embeddings:
        raise ValueError("schema must contain at least one document")

    cases: list[RetrievalCaseMetrics] = []
    for label in labels.cases:
        ranked = _rank_schema_embeddings(
            embeddings,
            provider.embed_query(label.question),
            top_k=top_k,
        )
        retrieved = {
            ColumnReference(
                schema_name=embedding.document.schema_name,
                table_name=embedding.document.table_name,
                column_name=embedding.document.column_name,
            )
            for embedding in ranked
            if embedding.document.column_name is not None
        }
        relevant = set(label.relevant_columns)
        hits = len(retrieved & relevant)
        cases.append(
            RetrievalCaseMetrics(
                id=label.id,
                precision=hits / len(ranked),
                recall=hits / len(relevant),
                relevant_retrieved=hits,
            )
        )

    return RetrievalMetrics(
        top_k=top_k,
        precision=sum(case.precision for case in cases) / len(cases),
        recall=sum(case.recall for case in cases) / len(cases),
        cases=tuple(cases),
    )


def compare_schema_retrieval(
    raw_schema: DatabaseSchema,
    enriched_schema: DatabaseSchema,
    labels: RetrievalLabelSet,
    provider: EvaluationEmbeddingProvider,
    *,
    top_k: int = 5,
) -> RetrievalComparison:
    """Evaluate raw and enriched schemas with the same provider and labels."""
    return RetrievalComparison(
        raw=evaluate_schema_retrieval(raw_schema, labels, provider, top_k=top_k),
        enriched=evaluate_schema_retrieval(enriched_schema, labels, provider, top_k=top_k),
    )


def _rank_schema_embeddings(
    embeddings: tuple[SchemaEmbedding, ...],
    query_vector: tuple[float, ...],
    *,
    top_k: int,
) -> tuple[SchemaEmbedding, ...]:
    if len(query_vector) != len(embeddings[0].vector):
        raise ValueError("query and document embedding dimensions must match")
    return tuple(
        sorted(
            embeddings,
            key=lambda embedding: (
                -_cosine_similarity(query_vector, embedding.vector),
                embedding.document.kind,
                embedding.document.schema_name,
                embedding.document.table_name,
                embedding.document.column_name or "",
            ),
        )[:top_k]
    )


def _cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions must match")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise ValueError("embedding vectors must not be zero vectors")
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare raw and enriched schema retrieval")
    parser.add_argument("database", type=Path, help="Existing wide-schema .duckdb path")
    parser.add_argument("enrichment", type=Path, help="Reviewed enrichment YAML")
    parser.add_argument("labels", type=Path, help="Versioned retrieval labels JSON")
    parser.add_argument("--top-k", type=int, default=5, help="Retrieval rank cutoff")
    args = parser.parse_args()

    with read_only_connection(args.database) as connection:
        raw_schema = introspect_schema(connection, sample_limit=0)
    enriched_schema = merge_schema_enrichment(raw_schema, load_schema_enrichment(args.enrichment))
    comparison = compare_schema_retrieval(
        raw_schema,
        enriched_schema,
        load_retrieval_labels(args.labels),
        DeterministicEmbeddingProvider(),
        top_k=args.top_k,
    )
    print(comparison.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
