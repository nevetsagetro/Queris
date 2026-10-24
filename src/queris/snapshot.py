"""Snapshot-first workspace and source materialization for local Queris discovery."""

import argparse
import hashlib
import shutil
import sqlite3
import tempfile
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import duckdb
import yaml
from pydantic import BaseModel, ConfigDict, Field

WorkspaceFormat = Literal["duckdb", "parquet", "csv", "zip", "sqlite"]
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024 * 1024


class SnapshotManifest(BaseModel):
    """Reproducible provenance for one locally materialized snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str = Field(min_length=1)
    name: str | None = None
    source: str = Field(min_length=1)
    source_name: str | None = None
    source_url: str | None = None
    license: str | None = None
    format: WorkspaceFormat
    raw_path: str
    database_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str | None = None
    schema_fingerprint: str | None = None
    discovered_at: datetime | None = None
    imported_at: datetime


class WorkspaceManifest(BaseModel):
    """Versioned registry for snapshots in a Queris workspace."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    snapshots: tuple[SnapshotManifest, ...] = ()


def init_workspace(workspace: str | Path) -> Path:
    """Create the local workspace directories without touching any database."""
    root = Path(workspace).expanduser().resolve()
    for directory in (".queris", "raw", "snapshots", "catalog", "intelligence", "cache"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    manifest_path = root / ".queris" / "manifest.yaml"
    if not manifest_path.exists():
        _write_manifest(manifest_path, WorkspaceManifest(version=1))
    return root


def import_snapshot(
    source: str | Path,
    workspace: str | Path,
    *,
    dataset_id: str,
    name: str | None = None,
    source_name: str | None = None,
    source_url: str | None = None,
    license: str | None = None,
    format: WorkspaceFormat | None = None,
    force: bool = False,
) -> SnapshotManifest:
    """Download or copy one source, materialize it, and register its provenance."""
    root = init_workspace(workspace)
    source_text = str(source)
    is_url = urllib.parse.urlparse(source_text).scheme in {"http", "https"}
    detected_format = format or _detect_format(source_text)
    suffix = _suffix_for(source_text, detected_format)
    raw_path = root / "raw" / f"{dataset_id}{suffix}"
    database_path = root / "snapshots" / f"{dataset_id}.duckdb"
    if (raw_path.exists() or database_path.exists()) and not force:
        raise FileExistsError(f"snapshot already exists for dataset: {dataset_id}")
    if is_url:
        _download(source_text, raw_path)
    else:
        source_path = Path(source_text).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"snapshot source does not exist: {source_path}")
        shutil.copy2(source_path, raw_path)
    _materialize(raw_path, database_path, detected_format, force=force)
    manifest = SnapshotManifest(
        dataset_id=dataset_id,
        name=name,
        source=source_text,
        source_name=source_name,
        source_url=source_url or (source_text if is_url else None),
        license=license,
        format=detected_format,
        raw_path=str(raw_path.relative_to(root)),
        database_path=str(database_path.relative_to(root)),
        sha256=_sha256(raw_path),
        imported_at=datetime.now(UTC),
    )
    _register_snapshot(root / ".queris" / "manifest.yaml", manifest)
    return manifest


def load_workspace_manifest(workspace: str | Path) -> WorkspaceManifest:
    """Load and validate the workspace registry."""
    path = Path(workspace).expanduser().resolve() / ".queris" / "manifest.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"workspace is not initialized: {path.parent.parent}")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return WorkspaceManifest.model_validate(document)


def _register_snapshot(path: Path, snapshot: SnapshotManifest) -> None:
    current = load_workspace_manifest(path.parent.parent)
    snapshots = tuple(item for item in current.snapshots if item.dataset_id != snapshot.dataset_id)
    _write_manifest(path, WorkspaceManifest(version=1, snapshots=(*snapshots, snapshot)))


def _write_manifest(path: Path, manifest: WorkspaceManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "queris-snapshot/1"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        total = 0
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise ValueError("snapshot exceeds the 2 GiB download limit")
            output.write(chunk)


def _materialize(
    raw_path: Path,
    database_path: Path,
    format: WorkspaceFormat,
    *,
    force: bool,
) -> None:
    if database_path.exists():
        if not force:
            raise FileExistsError(f"database already exists: {database_path}")
        database_path.unlink()
    if format == "duckdb":
        shutil.copy2(raw_path, database_path)
        return
    if format == "zip":
        _materialize_zip(raw_path, database_path)
        return
    if format == "sqlite":
        _materialize_sqlite(raw_path, database_path)
        return
    connection = duckdb.connect(str(database_path))
    try:
        function = "read_parquet" if format == "parquet" else "read_csv_auto"
        table_name = _table_name(raw_path.stem)
        options = ", sample_size=-1, header=true" if format == "csv" else ""
        connection.execute(
            f'CREATE TABLE "{_quote(table_name)}" AS SELECT * FROM {function}(?{options})',
            [str(raw_path)],
        )
    finally:
        connection.close()


def _materialize_zip(raw_path: Path, database_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="queris-snapshot-") as temporary:
        extracted = Path(temporary)
        with zipfile.ZipFile(raw_path) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            for member in members:
                target = (extracted / member.filename).resolve()
                if extracted not in target.parents:
                    raise ValueError("zip archive contains a path traversal entry")
            archive.extractall(extracted)
        csv_files = sorted(extracted.rglob("*.csv"))
        if not csv_files:
            raise ValueError("zip snapshot does not contain CSV files")
        connection = duckdb.connect(str(database_path))
        try:
            for csv_file in csv_files:
                table_name = _table_name(csv_file.stem)
                connection.execute(
                    (
                        f'CREATE TABLE "{_quote(table_name)}" AS '
                        "SELECT * FROM read_csv_auto(?, sample_size=-1)"
                    ),
                    [str(csv_file)],
                )
        finally:
            connection.close()


def _materialize_sqlite(raw_path: Path, database_path: Path) -> None:
    sqlite_connection = sqlite3.connect(raw_path)
    duck_connection = duckdb.connect(str(database_path))
    try:
        tables = sqlite_connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for (table_name,) in tables:
            columns = sqlite_connection.execute(
                f'PRAGMA table_info("{_quote(table_name)}")'
            ).fetchall()
            column_definitions = ", ".join(
                f'"{_quote(column[1])}" {_sqlite_type(column[2])}' for column in columns
            )
            duck_connection.execute(f'CREATE TABLE "{_quote(table_name)}" ({column_definitions})')
            rows = sqlite_connection.execute(f'SELECT * FROM "{_quote(table_name)}"').fetchall()
            if rows:
                placeholders = ", ".join("?" for _ in columns)
                duck_connection.executemany(
                    f'INSERT INTO "{_quote(table_name)}" VALUES ({placeholders})', rows
                )
    finally:
        sqlite_connection.close()
        duck_connection.close()


def _detect_format(source: str) -> WorkspaceFormat:
    suffix = Path(urllib.parse.urlparse(source).path).suffix.casefold()
    formats: dict[str, WorkspaceFormat] = {
        ".duckdb": "duckdb",
        ".parquet": "parquet",
        ".csv": "csv",
        ".zip": "zip",
        ".sqlite": "sqlite",
        ".db": "sqlite",
    }
    try:
        return formats[suffix]
    except KeyError as error:
        raise ValueError("could not detect snapshot format; use --format") from error


def _suffix_for(source: str, format: WorkspaceFormat) -> str:
    suffix = Path(urllib.parse.urlparse(source).path).suffix
    return suffix if suffix else f".{format}"


def _table_name(value: str) -> str:
    return value.replace("-", "_").replace(" ", "_") or "data"


def _quote(value: str) -> str:
    return value.replace('"', '""')


def _sqlite_type(value: str) -> str:
    upper = value.upper()
    if "INT" in upper:
        return "BIGINT"
    if any(token in upper for token in ("REAL", "FLOA", "DOUB")):
        return "DOUBLE"
    if any(token in upper for token in ("CHAR", "CLOB", "TEXT")):
        return "VARCHAR"
    if "BOOL" in upper:
        return "BOOLEAN"
    return "VARCHAR"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    """Initialize a workspace or import one snapshot."""
    parser = argparse.ArgumentParser(description="Manage local Queris snapshots")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init", help="initialize a .queris workspace")
    init_parser.add_argument("workspace", type=Path, nargs="?", default=Path("."))
    import_parser = subparsers.add_parser("import", help="download and materialize a snapshot")
    import_parser.add_argument("source")
    import_parser.add_argument("--workspace", type=Path, default=Path("."))
    import_parser.add_argument("--dataset-id", required=True)
    import_parser.add_argument("--name")
    import_parser.add_argument("--source-name")
    import_parser.add_argument("--source-url")
    import_parser.add_argument("--license")
    import_parser.add_argument("--format", choices=("duckdb", "parquet", "csv", "zip", "sqlite"))
    import_parser.add_argument("--force", action="store_true")
    discover_parser = subparsers.add_parser("discover", help="profile a registered snapshot")
    discover_parser.add_argument("--workspace", type=Path, default=Path("."))
    discover_parser.add_argument("--dataset-id", required=True)
    discover_parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    if args.command == "init":
        print(init_workspace(args.workspace))
        return
    if args.command == "discover":
        from queris.workspace_discovery import discover_snapshot

        print(
            discover_snapshot(
                args.workspace,
                args.dataset_id,
                sample_limit=args.samples,
            ).model_dump_json(indent=2)
        )
        return
    manifest = import_snapshot(
        args.source,
        args.workspace,
        dataset_id=args.dataset_id,
        name=args.name,
        source_name=args.source_name,
        source_url=args.source_url,
        license=args.license,
        format=args.format,
        force=args.force,
    )
    print(manifest.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
