import json
import sys
from pathlib import Path

import pytest

import queris.evaluation as evaluation
from queris.evaluation import (
    EvaluationCase,
    load_evaluation_cases,
    run_evaluation,
    summarize_evaluation,
    write_evaluation_records,
)
from queris.schema import DatabaseSchema

BASELINE_PATH = Path("evals/baseline_questions.json")


REFERENCE_SQL = {
    "total-orders": "SELECT COUNT(*) FROM orders",
    "total-revenue": "SELECT SUM(revenue) FROM order_items",
    "total-gross-profit": "SELECT SUM(revenue - cost) FROM order_items",
    "orders-by-region": """
        SELECT regions.name, COUNT(*)
        FROM orders
        JOIN regions USING (region_id)
        GROUP BY regions.name
    """,
    "revenue-by-category": """
        SELECT categories.name, SUM(order_items.revenue)
        FROM order_items
        JOIN products USING (product_id)
        JOIN categories USING (category_id)
        GROUP BY categories.name
    """,
    "negative-margin-categories": """
        SELECT categories.name, SUM(order_items.revenue - order_items.cost) AS profit
        FROM order_items
        JOIN products USING (product_id)
        JOIN categories USING (category_id)
        GROUP BY categories.name
        HAVING profit < 0
    """,
    "top-revenue-products": """
        WITH product_revenue AS (
            SELECT products.name, SUM(order_items.revenue) AS revenue
            FROM order_items
            JOIN products USING (product_id)
            GROUP BY products.name
        )
        SELECT name, revenue
        FROM product_revenue
        WHERE revenue = (SELECT MAX(revenue) FROM product_revenue)
    """,
    "second-quarter-revenue": """
        SELECT SUM(order_items.revenue)
        FROM order_items
        JOIN orders USING (order_id)
        WHERE order_date >= DATE '2026-04-01'
          AND order_date < DATE '2026-07-01'
    """,
    "quantity-by-product": """
        SELECT products.name, SUM(order_items.quantity)
        FROM order_items
        JOIN products USING (product_id)
        GROUP BY products.name
    """,
    "negative-margin-regions": """
        SELECT regions.name, SUM(order_items.revenue - order_items.cost) AS profit
        FROM order_items
        JOIN orders USING (order_id)
        JOIN regions USING (region_id)
        GROUP BY regions.name
        HAVING profit < 0
    """,
}


class ReferenceGenerator:
    def __init__(self, cases: tuple[EvaluationCase, ...]) -> None:
        self._sql_by_question = {case.question: REFERENCE_SQL[case.id] for case in cases}

    def generate_sql(self, schema: DatabaseSchema, question: str) -> str:
        return self._sql_by_question[question]


class UnsafeGenerator:
    def generate_sql(self, schema: DatabaseSchema, question: str) -> str:
        return "DROP TABLE orders"


def test_baseline_cases_are_unique_and_versioned() -> None:
    cases = load_evaluation_cases(BASELINE_PATH)

    assert len(cases) == 10
    assert len({case.id for case in cases}) == 10
    assert set(REFERENCE_SQL) == {case.id for case in cases}


def test_reference_queries_match_all_expected_results(sample_database: Path) -> None:
    cases = load_evaluation_cases(BASELINE_PATH)

    records = run_evaluation(
        sample_database,
        cases,
        ReferenceGenerator(cases),
        sample_limit=0,
    )
    summary = summarize_evaluation(records)

    assert summary.total == 10
    assert summary.correct == 10
    assert summary.passed is True
    assert all(record.error is None for record in records)


def test_run_evaluation_records_rejected_generated_sql(sample_database: Path) -> None:
    case = load_evaluation_cases(BASELINE_PATH)[0]

    [record] = run_evaluation(sample_database, (case,), UnsafeGenerator())

    assert record.generated_sql == "DROP TABLE orders"
    assert record.correct is False
    assert record.rows == ()
    assert record.error is not None
    assert record.error.startswith("SQLValidationError:")


def test_incomplete_evaluation_does_not_pass(sample_database: Path) -> None:
    cases = load_evaluation_cases(BASELINE_PATH)[:7]
    records = run_evaluation(sample_database, cases, ReferenceGenerator(cases))

    summary = summarize_evaluation(records)

    assert summary.correct == 7
    assert summary.passed is False


def test_write_evaluation_records_emits_jsonl(
    sample_database: Path,
    tmp_path: Path,
) -> None:
    cases = load_evaluation_cases(BASELINE_PATH)[:2]
    records = run_evaluation(sample_database, cases, ReferenceGenerator(cases))

    output_path = write_evaluation_records(tmp_path / "results" / "baseline.jsonl", records)
    lines = output_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["case_id"] == cases[0].id
    assert json.loads(lines[0])["generated_sql"] == REFERENCE_SQL[cases[0].id]


def test_load_evaluation_cases_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    case = {
        "id": "duplicate",
        "question": "Question?",
        "expected_column_count": 1,
        "expected_rows": [[1]],
    }
    path.write_text(json.dumps([case, case]), encoding="utf-8")

    with pytest.raises(ValueError, match="unique"):
        load_evaluation_cases(path)


def test_cli_writes_all_records_before_failed_exit(
    sample_database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "baseline.jsonl"
    monkeypatch.setattr(evaluation, "OpenAISQLGenerator", UnsafeGenerator)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "queris-eval",
            str(sample_database),
            "--questions",
            str(BASELINE_PATH),
            "--output",
            str(output_path),
            "--samples",
            "0",
        ],
    )

    with pytest.raises(SystemExit) as exit_info:
        evaluation.main()

    assert exit_info.value.code == 1
    assert len(output_path.read_text(encoding="utf-8").splitlines()) == 10
