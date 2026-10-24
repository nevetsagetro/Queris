"""Schema comparison and explicit snapshot refresh planning."""

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from queris.schema import DatabaseSchema
from queris.query_intelligence import selectively_refresh_query_intelligence
from queris.snapshot import SnapshotManifest, import_snapshot, load_workspace_manifest
from queris.workspace_discovery import discover_snapshot


class SchemaDrift(BaseModel):
    """Structural differences that can invalidate catalog intelligence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    added_tables: tuple[str, ...] = ()
    removed_tables: tuple[str, ...] = ()
    added_columns: tuple[str, ...] = ()
    removed_columns: tuple[str, ...] = ()
    changed_types: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(
            self.added_tables
            or self.removed_tables
            or self.added_columns
            or self.removed_columns
            or self.changed_types
        )

    @property
    def affected_tables(self) -> frozenset[str]:
        """Return table names whose intelligence may no longer be valid."""
        names = set(self.added_tables) | set(self.removed_tables)
        for reference in (*self.added_columns, *self.removed_columns, *self.changed_types):
            names.add(reference.split(".", 1)[0])
        return frozenset(names)


class RefreshPlan(BaseModel):
    """Dry-run or completed snapshot refresh result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    mode: Literal["dry_run", "refreshed"]
    source: str
    schema_changed: bool
    intelligence_needs_refresh: bool
    drift: SchemaDrift


def compare_schemas(previous: DatabaseSchema, current: DatabaseSchema) -> SchemaDrift:
    """Compare structural identifiers and types while ignoring sample values."""
    previous_tables = {table.name: table for table in previous.tables}
    current_tables = {table.name: table for table in current.tables}
    added_tables = tuple(sorted(set(current_tables) - set(previous_tables)))
    removed_tables = tuple(sorted(set(previous_tables) - set(current_tables)))
    added_columns: list[str] = []
    removed_columns: list[str] = []
    changed_types: list[str] = []
    for table_name in sorted(set(previous_tables) & set(current_tables)):
        old_columns = {column.name: column for column in previous_tables[table_name].columns}
        new_columns = {column.name: column for column in current_tables[table_name].columns}
        added_columns.extend(
            f"{table_name}.{name}" for name in sorted(set(new_columns) - set(old_columns))
        )
        removed_columns.extend(
            f"{table_name}.{name}" for name in sorted(set(old_columns) - set(new_columns))
        )
        changed_types.extend(
            f"{table_name}.{name}"
            for name in sorted(set(old_columns) & set(new_columns))
            if old_columns[name].data_type != new_columns[name].data_type
        )
    return SchemaDrift(
        added_tables=added_tables,
        removed_tables=removed_tables,
        added_columns=tuple(added_columns),
        removed_columns=tuple(removed_columns),
        changed_types=tuple(changed_types),
    )


def refresh_snapshot(
    workspace: str | Path,
    dataset_id: str,
    *,
    dry_run: bool = False,
) -> RefreshPlan:
    """Refresh one registered source and compare its schema to the previous catalog."""
    root = Path(workspace).expanduser().resolve()
    manifest = load_workspace_manifest(root)
    snapshot = _snapshot(manifest.snapshots, dataset_id)
    previous_path = root / "catalog" / f"{dataset_id}.schema.json"
    previous = (
        DatabaseSchema.model_validate_json(previous_path.read_text(encoding="utf-8"))
        if previous_path.is_file()
        else None
    )
    if dry_run:
        return RefreshPlan(
            dataset_id=dataset_id,
            mode="dry_run",
            source=snapshot.source,
            schema_changed=previous is None,
            intelligence_needs_refresh=previous is None,
            drift=SchemaDrift(),
        )
    refreshed_snapshot = import_snapshot(
        snapshot.source,
        root,
        dataset_id=dataset_id,
        source_name=snapshot.source_name,
        license=snapshot.license,
        format=snapshot.format,
        force=True,
    )
    report = discover_snapshot(root, dataset_id, sample_limit=3)
    current = DatabaseSchema.model_validate_json(
        (root / report.schema_path).read_text(encoding="utf-8")
    )
    drift = compare_schemas(previous, current) if previous else SchemaDrift()
    if drift.changed:
        _write_invalidation_marker(root, dataset_id, drift)
        intelligence_path = root / "intelligence" / f"{dataset_id}.queries.json"
        if intelligence_path.is_file() and previous is not None:
            selectively_refresh_query_intelligence(
                root / refreshed_snapshot.database_path,
                output=intelligence_path,
                previous=intelligence_path,
                affected_tables=set(drift.affected_tables),
            )
    return RefreshPlan(
        dataset_id=dataset_id,
        mode="refreshed",
        source=snapshot.source,
        schema_changed=drift.changed,
        intelligence_needs_refresh=drift.changed or previous is None,
        drift=drift,
    )


def _write_invalidation_marker(root: Path, dataset_id: str, drift: SchemaDrift) -> None:
    """Mark affected intelligence stale without deleting a reproducible previous artifact."""
    marker = root / "cache" / f"{dataset_id}.invalidation.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "dataset_id": dataset_id,
                "reason": "schema_drift",
                "drift": drift.model_dump(mode="json"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _snapshot(snapshots: tuple[SnapshotManifest, ...], dataset_id: str) -> SnapshotManifest:
    try:
        return next(item for item in snapshots if item.dataset_id == dataset_id)
    except StopIteration as error:
        raise ValueError(f"dataset is not registered in the workspace: {dataset_id}") from error


def main() -> None:
    """Plan or execute a registered snapshot refresh."""
    parser = argparse.ArgumentParser(description="Refresh and compare a Queris snapshot")
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(
        refresh_snapshot(args.workspace, args.dataset_id, dry_run=args.dry_run).model_dump_json(
            indent=2
        )
    )


if __name__ == "__main__":
    main()
