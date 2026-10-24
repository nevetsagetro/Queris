from pathlib import Path

import pytest

from queris.datasets import discover_datasets, select_dataset


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


def test_select_dataset_rejects_path_traversal(tmp_path: Path) -> None:
    (tmp_path / "safe.duckdb").touch()

    with pytest.raises(ValueError):
        select_dataset(tmp_path, "../safe.duckdb")
