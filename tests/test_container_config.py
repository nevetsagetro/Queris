from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_image_runs_api_as_non_root_with_container_defaults() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text()

    assert "FROM python:3.12-slim" in dockerfile
    assert "QUERIS_DATABASE=/data/retail.duckdb" in dockerfile
    assert "QUERIS_HOST=0.0.0.0" in dockerfile
    assert "USER queris" in dockerfile
    assert 'CMD ["queris-api"]' in dockerfile
    assert "database_available" in dockerfile


def test_compose_mounts_database_read_only_and_publishes_api() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "compose.yaml").read_text())
    api = config["services"]["api"]
    database_volume = api["volumes"][0]

    assert api["build"]["context"] == "."
    assert api["environment"]["QUERIS_DATABASE"] == "/data/retail.duckdb"
    assert api["ports"] == ["8000:8000"]
    assert database_volume["target"] == "/data/retail.duckdb"
    assert database_volume["read_only"] is True


def test_docker_context_excludes_local_data_and_credentials() -> None:
    ignored = set((PROJECT_ROOT / ".dockerignore").read_text().splitlines())

    assert {".git", ".venv", ".env", ".env.*", "*.duckdb", "data"} <= ignored
