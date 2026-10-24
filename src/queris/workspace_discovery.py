"""Deterministic discovery artifacts for local Queris snapshots."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from queris.catalog_profile import profile_database
from queris.database import read_only_connection
from queris.schema import DatabaseSchema, introspect_schema
from queris.snapshot import SnapshotManifest, WorkspaceManifest, load_workspace_manifest


class DiscoveryReport(BaseModel):
    """Summary written after a read-only structural discovery run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    discovered_at: datetime
    table_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    schema_path: str
    profile_path: str

    def human_summary(self) -> str:
        """Render a concise summary suitable for a terminal workflow."""
        return (
            f"Dataset: {self.dataset_id}\n"
            f"Tables: {self.table_count}\n"
            f"Relationships: {self.relationship_count}\n"
            f"Schema fingerprint: {self.schema_fingerprint}\n"
            f"Schema artifact: {self.schema_path}\n"
            f"Profile artifact: {self.profile_path}"
        )


def discover_snapshot(
    workspace: str | Path,
    dataset_id: str,
    *,
    sample_limit: int = 3,
) -> DiscoveryReport:
    """Write deterministic schema/profile artifacts without modifying the snapshot."""
    root = Path(workspace).expanduser().resolve()
    manifest = load_workspace_manifest(root)
    snapshot = _find_snapshot(manifest, dataset_id)
    database = root / snapshot.database_path
    with read_only_connection(database) as connection:
        schema = introspect_schema(connection, sample_limit=sample_limit)
    profile = profile_database(str(database))
    fingerprint = schema_fingerprint(schema)
    discovered_at = datetime.now(UTC)
    schema_path = root / "catalog" / f"{dataset_id}.schema.json"
    profile_path = root / "catalog" / f"{dataset_id}.profile.json"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(schema.model_dump_json(indent=2) + "\n", encoding="utf-8")
    profile_path.write_text(profile.model_dump_json(indent=2) + "\n", encoding="utf-8")
    updated = snapshot.model_copy(
        update={"schema_fingerprint": fingerprint, "discovered_at": discovered_at}
    )
    _update_snapshot(root / ".queris" / "manifest.yaml", manifest, updated)
    return DiscoveryReport(
        dataset_id=dataset_id,
        schema_fingerprint=fingerprint,
        discovered_at=discovered_at,
        table_count=len(schema.tables),
        relationship_count=len(profile.relationships),
        schema_path=str(schema_path.relative_to(root)),
        profile_path=str(profile_path.relative_to(root)),
    )


def _find_snapshot(manifest: WorkspaceManifest, dataset_id: str) -> SnapshotManifest:
    try:
        return next(item for item in manifest.snapshots if item.dataset_id == dataset_id)
    except StopIteration as error:
        raise ValueError(f"dataset is not registered in the workspace: {dataset_id}") from error


def schema_fingerprint(schema: DatabaseSchema) -> str:
    document = schema.model_dump(mode="json")
    for table in document["tables"]:
        for column in table["columns"]:
            column.pop("sample_values", None)
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _update_snapshot(path: Path, manifest: WorkspaceManifest, updated: SnapshotManifest) -> None:
    snapshots = tuple(
        updated if item.dataset_id == updated.dataset_id else item for item in manifest.snapshots
    )
    path.write_text(
        yaml.safe_dump(
            WorkspaceManifest(version=1, snapshots=snapshots).model_dump(mode="json"),
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def main() -> None:
    """Discover one registered snapshot from the command line."""
    parser = argparse.ArgumentParser(description="Discover a local Queris snapshot")
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args()
    report = discover_snapshot(args.workspace, args.dataset_id, sample_limit=args.samples)
    print(report.human_summary() if args.format == "text" else report.model_dump_json(indent=2))
