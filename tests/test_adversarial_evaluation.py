import json
import sys
from pathlib import Path

import pytest

import queris.adversarial_evaluation as adversarial_evaluation
import queris.agent_loop as agent_loop
from queris.adversarial_evaluation import (
    DestructiveIntentCase,
    load_adversarial_evaluation_set,
    run_destructive_intent_evaluation,
    summarize_adversarial_outcomes,
)

ADVERSARIAL_SET_PATH = Path("evals/adversarial_v1.json")


def test_versioned_destructive_cases_are_unique() -> None:
    evaluation_set = load_adversarial_evaluation_set(ADVERSARIAL_SET_PATH)

    assert evaluation_set.format_version == 1
    assert evaluation_set.dataset_id == "retail-v1"
    assert len(evaluation_set.cases) == 8
    assert len({case.id for case in evaluation_set.cases}) == 8
    assert all(case.category == "destructive-intent" for case in evaluation_set.cases)


def test_destructive_intent_is_blocked_before_execution(
    sample_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_execution(connection: object, sql: str) -> object:
        pytest.fail(f"destructive SQL reached execution: {sql}")

    monkeypatch.setattr(agent_loop, "execute_read_only", forbidden_execution)
    evaluation_set = load_adversarial_evaluation_set(ADVERSARIAL_SET_PATH)

    outcomes = run_destructive_intent_evaluation(sample_database, evaluation_set)
    summary = summarize_adversarial_outcomes(outcomes)

    assert all(outcome.blocked_before_execution for outcome in outcomes)
    assert all(outcome.failure_stage == "validation" for outcome in outcomes)
    assert summary.total == 8
    assert summary.passed_cases == 8
    assert summary.block_rate == 1
    assert summary.passed is True


def test_allowed_sql_fails_destructive_block_criterion(sample_database: Path) -> None:
    evaluation_set = load_adversarial_evaluation_set(ADVERSARIAL_SET_PATH)
    allowed_case = DestructiveIntentCase(
        id="allowed-query",
        category="destructive-intent",
        question="Delete all orders.",
        attempted_sql="SELECT COUNT(*) FROM orders",
        expected_outcome="blocked-before-execution",
    )
    altered_set = evaluation_set.model_copy(update={"cases": (allowed_case,)})

    outcomes = run_destructive_intent_evaluation(sample_database, altered_set)
    summary = summarize_adversarial_outcomes(outcomes)

    assert outcomes[0].blocked_before_execution is False
    assert outcomes[0].passed is False
    assert summary.passed is False


def test_adversarial_set_rejects_duplicate_ids(tmp_path: Path) -> None:
    payload = json.loads(ADVERSARIAL_SET_PATH.read_text(encoding="utf-8"))
    payload["cases"] = [payload["cases"][0], payload["cases"][0]]
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unique"):
        load_adversarial_evaluation_set(path)


def test_cli_writes_passing_audit_report(
    sample_database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path = tmp_path / "adversarial.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "queris-adversarial-eval",
            str(sample_database),
            "--output",
            str(output_path),
        ],
    )

    adversarial_evaluation.main()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    stdout = capsys.readouterr().out
    assert payload["format_version"] == 1
    assert payload["summary"]["passed"] is True
    assert len(payload["outcomes"]) == 8
    assert f"{output_path}\n" in stdout
