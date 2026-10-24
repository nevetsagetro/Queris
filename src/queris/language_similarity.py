"""Lightweight intent analysis and retrieval of similar validated questions."""

import json
import re
import unicodedata
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from queris.demo_examples import get_demo_examples
from queris.demo_registry import get_demo_definition


class QuestionIntent(BaseModel):
    """Structured, human-readable interpretation of a natural-language question."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    measure: str | None = None
    entity: str | None = None
    dimensions: tuple[str, ...] = ()
    filters: tuple[str, ...] = ()
    time_grain: str | None = None


class SimilarQuestion(BaseModel):
    """A curated question pattern retrieved for context or reuse."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str
    demo_id: str
    similarity: float = Field(ge=0, le=1)
    intent: QuestionIntent
    sql_hint: str | None = None


def analyze_question(question: str) -> QuestionIntent:
    """Extract coarse intent slots without invoking an external model."""
    normalized = _normalize(question)
    measure = _first_match(
        normalized, ("revenue", "sales", "orders", "order count", "average", "rate", "count")
    )
    entity = _first_match(
        normalized,
        ("customer", "product", "order", "country"),
    )
    dimensions = tuple(
        dimension
        for token, dimension in (
            ("country", "country"),
            ("product", "product"),
            ("customer", "customer"),
            ("month", "month"),
            ("year", "year"),
        )
        if token in normalized
    )
    filters = tuple(
        month
        for month in (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        )
        if month in normalized
    )
    time_grain = (
        "month" if "month" in normalized or filters else "year" if "year" in normalized else None
    )
    return QuestionIntent(
        measure=measure,
        entity=entity,
        dimensions=dimensions,
        filters=filters,
        time_grain=time_grain,
    )


def find_similar_questions(question: str, limit: int = 5) -> tuple[SimilarQuestion, ...]:
    """Rank curated questions by intent overlap and normalized token similarity."""
    target = analyze_question(question)
    target_tokens = set(_tokens(question))
    candidates: list[SimilarQuestion] = []
    for example in get_demo_examples():
        intent = analyze_question(example.question)
        score = _similarity(target, target_tokens, intent, set(_tokens(example.question)))
        if score < 0.35:
            continue
        definition = get_demo_definition(example.id)
        sql_hint = definition.sql_builder(definition.variant) if definition else None
        candidates.append(
            SimilarQuestion(
                question=example.question,
                demo_id=example.id,
                similarity=round(score, 3),
                intent=intent,
                sql_hint=sql_hint,
            )
        )
    return tuple(sorted(candidates, key=lambda item: (-item.similarity, item.demo_id))[:limit])


def find_similar_validated_questions(
    question: str,
    intelligence_path: str | Path,
    limit: int = 5,
) -> tuple[SimilarQuestion, ...]:
    """Retrieve similar questions from local, already validated intelligence."""
    path = Path(intelligence_path)
    if not path.is_file():
        return ()
    try:
        documents = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    target_tokens = set(_tokens(question))
    ranked: list[SimilarQuestion] = []
    for item in documents:
        candidate = str(item.get("question", ""))
        candidate_tokens = set(_tokens(candidate))
        if not candidate or not candidate_tokens:
            continue
        similarity = len(target_tokens & candidate_tokens) / max(
            len(target_tokens | candidate_tokens), 1
        )
        if similarity < 0.2:
            continue
        ranked.append(
            SimilarQuestion(
                question=candidate,
                demo_id=str(item.get("id", "")),
                similarity=similarity,
                intent=analyze_question(candidate),
                sql_hint=str(item.get("sql", "")) or None,
            )
        )
    ranked.sort(key=lambda item: item.similarity, reverse=True)
    return tuple(ranked[:limit])


def prompt_context(similar_questions: tuple[SimilarQuestion, ...]) -> str:
    """Render retrieved patterns as explicitly untrusted prompt context."""
    if not similar_questions:
        return ""
    rows = [
        {
            "question": item.question,
            "similarity": item.similarity,
            "intent": item.intent.model_dump(mode="json"),
            "validated_sql_pattern": item.sql_hint,
        }
        for item in similar_questions
    ]
    return "\n\n<similar_validated_patterns>\n" + repr(rows) + "\n</similar_validated_patterns>\n"


def _similarity(
    target: QuestionIntent,
    target_tokens: set[str],
    candidate: QuestionIntent,
    candidate_tokens: set[str],
) -> float:
    intent_score = (
        sum(
            (
                target.measure is not None and target.measure == candidate.measure,
                target.entity is not None and target.entity == candidate.entity,
                bool(set(target.dimensions) & set(candidate.dimensions)),
                target.time_grain is not None and target.time_grain == candidate.time_grain,
            )
        )
        / 4
    )
    token_score = len(target_tokens & candidate_tokens) / max(
        len(target_tokens | candidate_tokens), 1
    )
    return 0.7 * intent_score + 0.3 * token_score


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in normalized if not unicodedata.combining(character))


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", _normalize(value)))


def _first_match(value: str, candidates: tuple[str, ...]) -> str | None:
    return next((candidate for candidate in candidates if candidate in value), None)
