import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

import queris.evaluation_report as evaluation_report
from queris.adversarial_evaluation import (
    load_adversarial_evaluation_set,
    run_adversarial_evaluation,
)
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
from queris.wide_schema import create_wide_schema_database

EVALUATION_SET_PATH = Path("evals/retail_v1.json")
ADVERSARIAL_SET_PATH = Path("evals/adversarial_v1.json")
WIDE_ADVERSARIAL_SET_PATH = Path("evals/adversarial_wide_v1.json")
WIDE_ENRICHMENT_PATH = Path("metadata/wide-schema.v1.yaml")


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


def _adversarial_outcomes(sample_database: Path, wide_database: Path):
    retail_set = load_adversarial_evaluation_set(ADVERSARIAL_SET_PATH)
    wide_set = load_adversarial_evaluation_set(WIDE_ADVERSARIAL_SET_PATH)
    return run_adversarial_evaluation(
        sample_database,
        retail_set,
    ) + run_adversarial_evaluation(
        wide_database,
        wide_set,
        sample_limit=0,
        enrichment_path=WIDE_ENRICHMENT_PATH,
    )


def _report(sample_database: Path, wide_database: Path):
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
        _adversarial_outcomes(sample_database, wide_database),
        generated_at=datetime(2026, 6, 22, tzinfo=UTC),
    )


def test_report_composes_accuracy_safety_and_adversarial_outcomes(
    sample_database: Path,
    tmp_path: Path,
) -> None:
    report = _report(sample_database, create_wide_schema_database(tmp_path / "wide.duckdb"))

    assert report.format_version == 2
    assert report.dataset_id == "retail-v1"
    assert report.accuracy.total == 2
    assert report.accuracy.result_accuracy == 1
    assert report.safety.blocked_unsafe_query_rate == 1
    assert report.adversarial.total == 27
    assert report.adversarial.block_rate == 1
    assert report.adversarial.passed is True
    assert len(report.outcomes) == 2
    assert len(report.unsafe_query_outcomes) == 24
    assert len(report.adversarial_outcomes) == 27


def test_table_and_json_outputs_are_human_and_machine_readable(
    sample_database: Path,
    tmp_path: Path,
) -> None:
    report = _report(sample_database, create_wide_schema_database(tmp_path / "wide.duckdb"))

    table = format_evaluation_table(report)
    output_path = write_evaluation_report(tmp_path / "reports" / "phase6.json", report)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert "| Result accuracy           | 100.0%" in table
    assert "| Adversarial safety blocks | 100.0%" in table
    assert "| Adversarial criteria      | pass" in table
    assert "| Estimated cost            | n/a" in table
    assert payload["format_version"] == 2
    assert payload["generated_at"] == "2026-06-22T00:00:00Z"
    assert payload["outcomes"][0]["case_id"] == "total-orders"


def test_cli_runs_full_set_and_writes_report(
    sample_database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path = tmp_path / "phase6.json"
    history_directory = tmp_path / "history"
    wide_database = create_wide_schema_database(tmp_path / "wide.duckdb")
    monkeypatch.setattr(evaluation_report, "GeminiSQLGenerator", ReferenceGenerator)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "queris-evaluation-report",
            str(sample_database),
            "--output",
            str(output_path),
            "--history-dir",
            str(history_directory),
            "--wide-database",
            str(wide_database),
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
    assert payload["adversarial"]["total"] == 27
    assert payload["adversarial"]["passed"] is True
    assert len(payload["adversarial_outcomes"]) == 27
    assert "Execution accuracy" in stdout
    assert "Historical comparison: no compatible previous report" in stdout
    assert f"JSON report: {output_path}" in stdout
    assert len(tuple(history_directory.glob("*.json"))) == 1


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
