from pathlib import Path

import duckdb
import yaml

from queris.dataset_workflow import (
    validate_dataset_workflow,
    write_enrichment_draft,
    write_source_manifest,
)
from queris.datasets import discover_datasets


def _database(path: Path) -> Path:
    connection = duckdb.connect(str(path))
    connection.execute("CREATE TABLE events (event_id INTEGER, category VARCHAR, value DOUBLE)")
    connection.execute("INSERT INTO events VALUES (1, 'a', 2.5), (2, 'b', 4.0)")
    connection.close()
    return path


def test_workflow_generates_and_executes_starters_for_unknown_schema(tmp_path: Path) -> None:
    database = _database(tmp_path / "example.duckdb")

    report = validate_dataset_workflow(database, metadata_directory=tmp_path / "metadata")

    assert report.table_count == 1
    assert report.demo_validation.total >= 50
    assert report.demo_validation.passed == report.demo_validation.total
    assert report.ready is True


def test_source_manifest_is_visible_to_dataset_discovery(tmp_path: Path) -> None:
    database = _database(tmp_path / "example.duckdb")
    metadata = tmp_path / "metadata"

    write_source_manifest(
        database,
        metadata,
        name="Example Dataset",
        source_name="Public publisher",
        source_url="https://example.org/dataset",
        license="Open terms",
    )

    [dataset] = discover_datasets(tmp_path, database, metadata)
    assert dataset.name == "Example Dataset"
    assert dataset.source_url == "https://example.org/dataset"
    assert dataset.license == "Open terms"


def test_enrichment_draft_is_explicit_and_does_not_change_database(tmp_path: Path) -> None:
    database = _database(tmp_path / "example.duckdb")
    draft_path = tmp_path / "metadata" / "example.v1.yaml"

    write_enrichment_draft(database, draft_path)

    draft = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
    assert draft["reviewed"] is False
    assert database.stat().st_size > 0
