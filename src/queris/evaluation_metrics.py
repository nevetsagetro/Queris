"""Execution and result accuracy metrics for versioned evaluation sets."""

from itertools import permutations
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from queris.agent_loop import (
    DEFAULT_MAX_RETRIES,
    CorrectingSQLGenerator,
    FailureStage,
    run_agent_loop,
)
from queris.evaluation_set import EvaluationCategory, EvaluationSet, EvaluationSetCase
from queris.pipeline import FullSchemaSelector
from queris.result_matching import rows_match


class EvaluationOutcome(BaseModel):
    """Auditable execution and result outcome for one Phase 6 case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    category: EvaluationCategory
    question: str
    final_sql: str | None = None
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    execution_succeeded: bool
    result_correct: bool
    retry_count: int = Field(ge=0)
    failure_stage: FailureStage | None = None
    retries_exhausted: bool = False
    error: str | None = None

    @model_validator(mode="after")
    def require_executed_correct_result(self) -> Self:
        if self.result_correct and not self.execution_succeeded:
            raise ValueError("correct result requires successful execution")
        return self


class AccuracyMetrics(BaseModel):
    """Aggregate execution and result accuracy over all attempted cases."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total: int = Field(ge=0)
    execution_successes: int = Field(ge=0)
    correct_results: int = Field(ge=0)
    execution_accuracy: float = Field(ge=0, le=1)
    result_accuracy: float = Field(ge=0, le=1)


def run_accuracy_evaluation(
    database_path: str | Path,
    evaluation_set: EvaluationSet,
    generator: CorrectingSQLGenerator,
    *,
    sample_limit: int = 3,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> tuple[EvaluationOutcome, ...]:
    """Run every versioned case independently through the bounded agent loop."""
    outcomes = []
    for case in evaluation_set.cases:
        try:
            result = run_agent_loop(
                database_path,
                case.question,
                generator,
                FullSchemaSelector(),
                sample_limit=sample_limit,
                max_retries=max_retries,
            )
        except Exception as error:
            outcomes.append(
                EvaluationOutcome(
                    case_id=case.id,
                    category=case.category,
                    question=case.question,
                    execution_succeeded=False,
                    result_correct=False,
                    retry_count=0,
                    error=f"{type(error).__name__}: {error}",
                )
            )
            continue

        execution_succeeded = result.status == "success"
        outcomes.append(
            EvaluationOutcome(
                case_id=case.id,
                category=case.category,
                question=case.question,
                final_sql=result.sql,
                columns=result.columns,
                rows=result.rows,
                execution_succeeded=execution_succeeded,
                result_correct=execution_succeeded
                and matches_evaluation_result(case, result.columns, result.rows),
                retry_count=result.retry_count,
                failure_stage=result.failure_stage,
                retries_exhausted=result.retries_exhausted,
                error=result.error,
            )
        )
    return tuple(outcomes)


def matches_evaluation_result(
    case: EvaluationSetCase,
    columns: tuple[str, ...],
    rows: tuple[tuple[Any, ...], ...],
) -> bool:
    """Match expected values while allowing row and column order differences."""
    column_count = len(case.expected_columns)
    if len(columns) != column_count or any(len(row) != column_count for row in rows):
        return False
    for column_order in permutations(range(column_count)):
        reordered_rows = tuple(tuple(row[index] for index in column_order) for row in rows)
        if rows_match(reordered_rows, case.expected_rows):
            return True
    return False


def summarize_accuracy(outcomes: tuple[EvaluationOutcome, ...]) -> AccuracyMetrics:
    """Calculate execution and result accuracy over all attempted cases."""
    total = len(outcomes)
    execution_successes = sum(outcome.execution_succeeded for outcome in outcomes)
    correct_results = sum(outcome.result_correct for outcome in outcomes)
    return AccuracyMetrics(
        total=total,
        execution_successes=execution_successes,
        correct_results=correct_results,
        execution_accuracy=execution_successes / total if total else 0,
        result_accuracy=correct_results / total if total else 0,
    )
