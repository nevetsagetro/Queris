from pathlib import Path

import pytest

import queris.online_retail as online_retail


def test_download_online_retail_reuses_existing_workbook(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    workbook = raw_dir / online_retail.DEFAULT_XLSX_NAME
    workbook.write_bytes(b"local workbook")

    def fail_download(*args: object, **kwargs: object) -> None:
        pytest.fail("existing workbook should be reused")

    monkeypatch.setattr(online_retail.urllib.request, "urlretrieve", fail_download)
    assert online_retail.download_online_retail(raw_dir) == workbook


def test_database_builder_refuses_to_replace_existing_output(tmp_path: Path) -> None:
    workbook = tmp_path / "Online Retail.xlsx"
    workbook.write_bytes(b"not parsed because output already exists")
    database = tmp_path / "retail.duckdb"
    database.write_bytes(b"existing")

    with pytest.raises(FileExistsError, match="refusing to replace"):
        online_retail.create_online_retail_database(workbook, database)
