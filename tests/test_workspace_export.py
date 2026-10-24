import zipfile
from pathlib import Path

from queris.snapshot import import_snapshot
from queris.workspace_export import export_workspace


def test_export_omits_snapshot_by_default(tmp_path: Path) -> None:
    source = tmp_path / "events.csv"
    source.write_text("event_id,category\n1,a\n2,b\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    import_snapshot(source, workspace, dataset_id="events")
    catalog = workspace / "catalog"
    catalog.mkdir(exist_ok=True)
    (catalog / "events.schema.json").write_text("{}", encoding="utf-8")

    output = tmp_path / "export.zip"
    report = export_workspace(workspace, "events", output)

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
    assert report.includes_snapshot is False
    assert "snapshots/events.duckdb" not in names
    assert ".queris/manifest.yaml" in names
    assert "catalog/events.schema.json" in names
    assert "export.json" in names
