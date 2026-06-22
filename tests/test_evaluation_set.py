import json
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from queris.database import execute_read_only, read_only_connection
from queris.evaluation_set import EvaluationSet, load_evaluation_set

EVALUATION_SET_PATH = Path("evals/retail_v1.json")
REQUIRED_CATEGORIES = {
    "simple-aggregation",
    "multi-table-join",
    "time-filtering",
    "group-by-having",
    "nested-subquery",
}


def _normalized_rows(rows: tuple[tuple[object, ...], ...]) -> Counter[tuple[object, ...]]:
    return Counter(tuple(_normalized_value(value) for value in row) for row in rows)


def _normalized_value(value: object) -> object:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).normalize()
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def test_retail_evaluation_set_is_versioned_unique_and_covers_required_categories() -> None:
    evaluation_set = load_evaluation_set(EVALUATION_SET_PATH)

    assert evaluation_set.format_version == 1
    assert evaluation_set.dataset_id == "retail-v1"
    assert len(evaluation_set.cases) == 50
    assert len({case.id for case in evaluation_set.cases}) == 50
    assert {case.category for case in evaluation_set.cases} == REQUIRED_CATEGORIES


def test_reference_queries_match_reviewed_results(sample_database: Path) -> None:
    evaluation_set = load_evaluation_set(EVALUATION_SET_PATH)

    with read_only_connection(sample_database) as connection:
        for case in evaluation_set.cases:
            cursor = execute_read_only(connection, case.expected_sql)
            columns = tuple(description[0] for description in cursor.description or ())
            rows = tuple(tuple(row) for row in cursor.fetchall())

            assert columns == case.expected_columns, case.id
            assert _normalized_rows(rows) == _normalized_rows(case.expected_rows), case.id


def test_evaluation_set_rejects_duplicate_case_ids() -> None:
    raw_set = json.loads(EVALUATION_SET_PATH.read_text(encoding="utf-8"))
    raw_set["cases"].append(raw_set["cases"][0])

    with pytest.raises(ValidationError, match="case ids must be unique"):
        EvaluationSet.model_validate(raw_set)


def test_evaluation_set_rejects_inconsistent_expected_row_width() -> None:
    raw_set = json.loads(EVALUATION_SET_PATH.read_text(encoding="utf-8"))
    raw_set["cases"][0]["expected_rows"] = [[4, "unexpected"]]

    with pytest.raises(ValidationError, match="row width"):
        EvaluationSet.model_validate(raw_set)


def test_evaluation_set_rejects_unsafe_reference_sql() -> None:
    raw_set = json.loads(EVALUATION_SET_PATH.read_text(encoding="utf-8"))
    raw_set["cases"][0]["expected_sql"] = "DROP TABLE orders"

    with pytest.raises(ValidationError, match="Only SELECT"):
        EvaluationSet.model_validate(raw_set)
