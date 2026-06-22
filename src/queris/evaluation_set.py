"""Versioned Phase 6 evaluation-set contract."""

import json
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from queris.sql_validation import parse_read_only

EvaluationCategory = Literal[
    "simple-aggregation",
    "multi-table-join",
    "time-filtering",
    "group-by-having",
    "nested-subquery",
]
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EvaluationSetCase(BaseModel):
    """One reviewed natural-language question and its reference outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    category: EvaluationCategory
    question: NonEmptyString
    expected_sql: NonEmptyString
    expected_columns: tuple[NonEmptyString, ...] = Field(min_length=1)
    expected_rows: tuple[tuple[Any, ...], ...]

    @field_validator("expected_sql")
    @classmethod
    def require_read_only_reference_sql(cls, sql: str) -> str:
        parse_read_only(sql)
        return sql

    @model_validator(mode="after")
    def require_consistent_row_width(self) -> Self:
        column_count = len(self.expected_columns)
        if any(len(row) != column_count for row in self.expected_rows):
            raise ValueError("expected row width must match expected columns")
        return self


class EvaluationSet(BaseModel):
    """One immutable, versioned collection of reviewed evaluation cases."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal[1]
    dataset_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    fixture: NonEmptyString
    cases: tuple[EvaluationSetCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_case_ids(self) -> Self:
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation set case ids must be unique")
        return self


def load_evaluation_set(path: str | Path) -> EvaluationSet:
    """Load and validate one versioned JSON evaluation set."""
    raw_set = json.loads(Path(path).read_text(encoding="utf-8"))
    return EvaluationSet.model_validate(raw_set)
