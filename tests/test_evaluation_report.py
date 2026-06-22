import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

import queris.evaluation_report as evaluation_report
from queris.evaluation_metrics import run_accuracy_evaluation
from queris.evaluation_report import (
    compose_evaluation_report,
    format_evaluation_table,
    write_evaluation_report,
)
from queris.evaluation_set import EvaluationSet, load_evaluation_set
from queris.generation import SQLCorrectionContext
from queris.safety_evaluation import evaluate_unsafe_queries
from queris.schema import DatabaseSchema

EVALUATION_SET_PATH = Path("evals/retail_v1.json")


class ReferenceGenerator:
    def __init__(self, evaluation_set: EvaluationSet | None = None) -> None:
        evaluation_set = evaluation_set or load_evaluation_set(EVALUATION_SET_PATH)
        self._case_by_question = {case.question: case for case in evaluation_set.cases}

    def generate_sql(
        self,
        schema: DatabaseSchema,
        question: str,
        correction: SQLCorrectionContext | None = None,
    ) -> str:
        return self._case_by_question[question].expected_sql


def _report(sample_database: Path):
    evaluation_set = load_evaluation_set(EVALUATION_SET_PATH)
    subset = evaluation_set.model_copy(update={"cases": evaluation_set.cases[:2]})
    outcomes = run_accuracy_evaluation(
        sample_database,
        subset,
        ReferenceGenerator(subset),
        sample_limit=0,
    )
    return compose_evaluation_report(
        subset,
        outcomes,
        evaluate_unsafe_queries(),
        generated_at=datetime(2026, 6, 22, tzinfo=UTC),
    )


def test_report_composes_accuracy_safety_and_audit_outcomes(sample_database: Path) -> None:
    report = _report(sample_database)

    assert report.format_version == 1
    assert report.dataset_id == "retail-v1"
    assert report.accuracy.total == 2
    assert report.accuracy.result_accuracy == 1
    assert report.safety.blocked_unsafe_query_rate == 1
    assert len(report.outcomes) == 2
    assert len(report.unsafe_query_outcomes) == 24


def test_table_and_json_outputs_are_human_and_machine_readable(
    sample_database: Path,
    tmp_path: Path,
) -> None:
    report = _report(sample_database)

    table = format_evaluation_table(report)
    output_path = write_evaluation_report(tmp_path / "reports" / "phase6.json", report)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert "| Result accuracy        | 100.0%" in table
    assert "| Estimated cost         | n/a" in table
    assert payload["format_version"] == 1
    assert payload["generated_at"] == "2026-06-22T00:00:00Z"
    assert payload["outcomes"][0]["case_id"] == "total-orders"


def test_cli_runs_full_set_and_writes_report(
    sample_database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path = tmp_path / "phase6.json"
    monkeypatch.setattr(evaluation_report, "GeminiSQLGenerator", ReferenceGenerator)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "queris-evaluation-report",
            str(sample_database),
            "--output",
            str(output_path),
            "--samples",
            "0",
        ],
    )

    evaluation_report.main()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    stdout = capsys.readouterr().out
    assert payload["accuracy"]["total"] == 50
    assert payload["accuracy"]["correct_results"] == 50
    assert payload["safety"]["blocked"] == 24
    assert "Execution accuracy" in stdout
    assert f"JSON report: {output_path}" in stdout


def test_cli_requires_token_rates_as_a_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "queris-evaluation-report",
            "retail.duckdb",
            "--input-usd-per-million",
            "1.25",
        ],
    )

    with pytest.raises(SystemExit) as exit_info:
        evaluation_report.main()

    assert exit_info.value.code == 2
