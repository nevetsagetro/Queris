import csv
import sqlite3
import zipfile
from pathlib import Path

import duckdb
import yaml

from queris.snapshot import import_snapshot, init_workspace, load_workspace_manifest
from queris.workspace_discovery import discover_snapshot


def _assert_snapshot(workspace: Path, dataset_id: str, table_name: str) -> None:
    manifest = load_workspace_manifest(workspace)
    snapshot = next(item for item in manifest.snapshots if item.dataset_id == dataset_id)
    assert snapshot.database_path == f"snapshots/{dataset_id}.duckdb"
    connection = duckdb.connect(str(workspace / snapshot.database_path), read_only=True)
    try:
        assert connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0] == 2
    finally:
        connection.close()


def test_init_workspace_creates_local_layout(tmp_path: Path) -> None:
    workspace = init_workspace(tmp_path / "workspace")

    assert (workspace / ".queris" / "manifest.yaml").is_file()
    assert (workspace / "snapshots").is_dir()
    assert yaml.safe_load((workspace / ".queris" / "manifest.yaml").read_text()) == {
        "version": 1,
        "snapshots": [],
    }


def test_import_csv_materializes_and_registers_checksum(tmp_path: Path) -> None:
    source = tmp_path / "events.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows((("event_id", "category"), (1, "a"), (2, "b")))

    workspace = tmp_path / "workspace"
    manifest = import_snapshot(source, workspace, dataset_id="events", source_name="Test source")

    assert manifest.format == "csv"
    assert len(manifest.sha256) == 64
    _assert_snapshot(workspace, "events", "events")


def test_import_parquet_materializes(tmp_path: Path) -> None:
    source = tmp_path / "events.parquet"
    connection = duckdb.connect(str(tmp_path / "source.duckdb"))
    connection.execute("CREATE TABLE events (event_id INTEGER, category VARCHAR)")
    connection.execute("INSERT INTO events VALUES (1, 'a'), (2, 'b')")
    connection.execute("COPY events TO ? (FORMAT PARQUET)", [str(source)])
    connection.close()

    workspace = tmp_path / "workspace"
    import_snapshot(source, workspace, dataset_id="events")

    _assert_snapshot(workspace, "events", "events")


def test_import_zip_materializes_each_csv_as_a_table(tmp_path: Path) -> None:
    csv_path = tmp_path / "orders.csv"
    csv_path.write_text("order_id\n1\n2\n", encoding="utf-8")
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.write(csv_path, "nested/orders.csv")

    workspace = tmp_path / "workspace"
    import_snapshot(archive, workspace, dataset_id="orders")

    _assert_snapshot(workspace, "orders", "orders")


def test_import_sqlite_does_not_modify_source(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    sqlite_connection = sqlite3.connect(source)
    sqlite_connection.execute("CREATE TABLE orders (order_id INTEGER, category TEXT)")
    sqlite_connection.execute("INSERT INTO orders VALUES (1, 'a'), (2, 'b')")
    sqlite_connection.commit()
    sqlite_connection.close()
    original_bytes = source.read_bytes()

    workspace = tmp_path / "workspace"
    import_snapshot(source, workspace, dataset_id="orders")

    assert source.read_bytes() == original_bytes
    _assert_snapshot(workspace, "orders", "orders")


def test_discover_snapshot_writes_catalog_and_fingerprint(tmp_path: Path) -> None:
    source = tmp_path / "events.csv"
    source.write_text("event_id,category\n1,a\n2,b\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    import_snapshot(source, workspace, dataset_id="events")

    report = discover_snapshot(workspace, "events", sample_limit=0)
    manifest = load_workspace_manifest(workspace)
    snapshot = manifest.snapshots[0]

    assert report.table_count == 1
    assert report.relationship_count == 0
    assert len(report.schema_fingerprint) == 64
    assert snapshot.schema_fingerprint == report.schema_fingerprint
    assert (workspace / report.schema_path).is_file()
    assert (workspace / report.profile_path).is_file()
