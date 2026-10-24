from pathlib import Path

import pytest

from queris.datasets import discover_datasets, select_dataset
from queris.snapshot import import_snapshot


def test_discover_datasets_exposes_only_local_duckdb_files(tmp_path: Path) -> None:
    active = tmp_path / "active.duckdb"
    other = tmp_path / "other.duckdb"
    active.touch()
    other.touch()
    (tmp_path / "notes.txt").touch()

    datasets = discover_datasets(tmp_path, active)

    assert [item.id for item in datasets] == ["active.duckdb", "other.duckdb"]
    assert datasets[0].active is True
    assert datasets[1].active is False


def test_discover_datasets_exposes_public_provenance_for_known_sources(tmp_path: Path) -> None:
    dataset = tmp_path / "chinook.duckdb"
    dataset.touch()

    [info] = discover_datasets(tmp_path, dataset)

    assert info.name == "Chinook Database"
    assert info.source_name == "Chinook database project"
    assert info.source_url is not None
    assert info.license == "MIT"


def test_select_dataset_rejects_path_traversal(tmp_path: Path) -> None:
    (tmp_path / "safe.duckdb").touch()

    with pytest.raises(ValueError):
        select_dataset(tmp_path, "../safe.duckdb")


def test_discovery_reads_public_provenance_from_snapshot_workspace(tmp_path: Path) -> None:
    source = tmp_path / "events.csv"
    source.write_text("event_id\n1\n2\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    import_snapshot(
        source,
        workspace,
        dataset_id="events",
        name="Public Events",
        source_name="Public publisher",
        source_url="https://example.org/events.csv",
    )

    [dataset] = discover_datasets(
        workspace / "snapshots",
        workspace / "snapshots" / "events.duckdb",
        workspace=workspace,
    )

    assert dataset.name == "Public Events"
    assert dataset.source_url == "https://example.org/events.csv"
