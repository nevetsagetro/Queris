import json
from pathlib import Path

import pytest

from queris.agent_evaluation import (
    AGENT_EVAL_PASS_COUNT,
    AgentEvaluationCase,
    load_agent_evaluation_cases,
    run_agent_evaluation,
    summarize_agent_evaluation,
    write_agent_evaluation_records,
)
from queris.generation import SQLCorrectionContext
from queris.schema import DatabaseSchema

AGENT_EVAL_PATH = Path("evals/agent_loop_questions.json")

REFERENCE_SQL = {
    "recover-total-orders": "SELECT COUNT(*) FROM orders",
    "recover-total-revenue": "SELECT SUM(revenue) FROM order_items",
    "recover-orders-by-region": """
        SELECT regions.name, COUNT(*)
        FROM orders JOIN regions USING (region_id)
        GROUP BY regions.name
    """,
    "recover-revenue-by-category": """
        SELECT categories.name, SUM(order_items.revenue)
        FROM order_items
        JOIN products USING (product_id)
        JOIN categories USING (category_id)
        GROUP BY categories.name
    """,
    "recover-negative-margin-regions": """
        SELECT regions.name, SUM(order_items.revenue - order_items.cost)
        FROM order_items
        JOIN orders USING (order_id)
        JOIN regions USING (region_id)
        GROUP BY regions.name
        HAVING SUM(order_items.revenue - order_items.cost) < 0
    """,
}


class ReferenceCorrector:
    def __init__(self, cases: tuple[AgentEvaluationCase, ...]) -> None:
        self._case_by_question = {case.question: case for case in cases}
        self.corrections: list[SQLCorrectionContext] = []

    def generate_sql(
        self,
        schema: DatabaseSchema,
        question: str,
        correction: SQLCorrectionContext | None = None,
    ) -> str:
        assert correction is not None
        self.corrections.append(correction)
        return REFERENCE_SQL[self._case_by_question[question].id]


class WrongCorrector:
    def generate_sql(
        self,
        schema: DatabaseSchema,
        question: str,
        correction: SQLCorrectionContext | None = None,
    ) -> str:
        return "SELECT 1"


def test_agent_evaluation_cases_are_unique_and_versioned() -> None:
    cases = load_agent_evaluation_cases(AGENT_EVAL_PATH)

    assert len(cases) == 5
    assert len({case.id for case in cases}) == 5
    assert set(REFERENCE_SQL) == {case.id for case in cases}


def test_reference_corrections_pass_exit_threshold(sample_database: Path) -> None:
    cases = load_agent_evaluation_cases(AGENT_EVAL_PATH)
    corrector = ReferenceCorrector(cases)

    records = run_agent_evaluation(sample_database, cases, corrector, sample_limit=0)
    summary = summarize_agent_evaluation(records)

    assert summary.total == 5
    assert summary.correct == 5
    assert summary.required == AGENT_EVAL_PASS_COUNT
    assert summary.passed is True
    assert all(record.recovered and record.correct for record in records)
    assert all(record.retry_count == 1 for record in records)
    assert len(corrector.corrections) == 5


def test_executable_wrong_corrections_do_not_count_as_correct(sample_database: Path) -> None:
    cases = load_agent_evaluation_cases(AGENT_EVAL_PATH)

    records = run_agent_evaluation(sample_database, cases, WrongCorrector(), sample_limit=0)
    summary = summarize_agent_evaluation(records)

    assert all(record.recovered for record in records)
    assert not any(record.correct for record in records)
    assert summary.passed is False


def test_incomplete_agent_evaluation_does_not_pass(sample_database: Path) -> None:
    cases = load_agent_evaluation_cases(AGENT_EVAL_PATH)[:AGENT_EVAL_PASS_COUNT]
    records = run_agent_evaluation(sample_database, cases, ReferenceCorrector(cases))

    summary = summarize_agent_evaluation(records)

    assert summary.correct == AGENT_EVAL_PASS_COUNT
    assert summary.passed is False


def test_write_agent_evaluation_records_emits_jsonl(
    sample_database: Path,
    tmp_path: Path,
) -> None:
    cases = load_agent_evaluation_cases(AGENT_EVAL_PATH)[:2]
    records = run_agent_evaluation(sample_database, cases, ReferenceCorrector(cases))

    output_path = write_agent_evaluation_records(tmp_path / "agent.jsonl", records)
    lines = output_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["case_id"] == cases[0].id
    assert json.loads(lines[0])["retry_count"] == 1


def test_load_agent_evaluation_cases_rejects_duplicate_ids(tmp_path: Path) -> None:
    case = {
        "id": "duplicate",
        "question": "Question?",
        "initial_sql": "SELECT missing",
        "expected_column_count": 1,
        "expected_rows": [[1]],
    }
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps([case, case]), encoding="utf-8")

    with pytest.raises(ValueError, match="unique"):
        load_agent_evaluation_cases(path)
