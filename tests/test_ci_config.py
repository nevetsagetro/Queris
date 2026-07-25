from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_quality_workflow() -> dict[str, object]:
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "quality.yml"
    return yaml.load(workflow_path.read_text(), Loader=yaml.BaseLoader)


def test_quality_workflow_runs_for_pull_requests_to_main() -> None:
    workflow = load_quality_workflow()

    assert workflow["on"]["pull_request"]["branches"] == ["main"]
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["permissions"] == {"contents": "read"}


def test_quality_workflow_uses_cached_supported_python() -> None:
    steps = load_quality_workflow()["jobs"]["checks"]["steps"]
    checkout = steps[0]
    setup_python = steps[1]

    assert checkout["uses"] == "actions/checkout@v7"
    assert checkout["with"]["persist-credentials"] == "false"
    assert setup_python["uses"] == "actions/setup-python@v6"
    assert setup_python["with"] == {
        "python-version": "3.12",
        "cache": "pip",
        "cache-dependency-path": "pyproject.toml",
    }


def test_quality_workflow_matches_local_verification_commands() -> None:
    steps = load_quality_workflow()["jobs"]["checks"]["steps"]
    commands = {step["name"]: step["run"] for step in steps if "run" in step}

    assert commands["Install package and development tools"] == "python -m pip install -e '.[dev]'"
    assert commands["Run repository hooks"] == "pre-commit run --all-files"
    assert commands["Run unit tests"] == "python -m pytest"
    assert commands["Run Phase 6/7 evaluation gate"] == "queris-ci-eval"
    assert "docker compose up --build --detach --wait" in commands["Start containerized API"]
    assert commands["Stop containerized API"] == "docker compose down"
    stop_step = next(step for step in steps if step["name"] == "Stop containerized API")
    assert stop_step["if"] == "always()"
