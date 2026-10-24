"""Export reproducible local discovery artifacts without exporting raw data by default."""

import argparse
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from queris.snapshot import load_workspace_manifest


class WorkspaceExport(BaseModel):
    """Description of one exported discovery package."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    output_path: str
    included_files: tuple[str, ...]
    includes_snapshot: bool
    exported_at: datetime


def export_workspace(
    workspace: str | Path,
    dataset_id: str,
    output: str | Path,
    *,
    include_snapshot: bool = False,
    force: bool = False,
) -> WorkspaceExport:
    """Zip catalog and validated intelligence artifacts, omitting raw data by default."""
    root = Path(workspace).expanduser().resolve()
    destination = Path(output).expanduser().resolve()
    if destination.exists() and not force:
        raise FileExistsError(f"export already exists: {destination}")
    manifest = load_workspace_manifest(root)
    snapshot = next((item for item in manifest.snapshots if item.dataset_id == dataset_id), None)
    if snapshot is None:
        raise ValueError(f"dataset is not registered in the workspace: {dataset_id}")
    candidates = [
        root / ".queris" / "manifest.yaml",
        root / "catalog" / f"{dataset_id}.schema.json",
        root / "catalog" / f"{dataset_id}.profile.json",
        root / "intelligence" / f"{dataset_id}.queries.json",
    ]
    if include_snapshot:
        candidates.append(root / snapshot.database_path)
    files = [path for path in candidates if path.is_file()]
    if not files:
        raise ValueError("workspace has no discovery artifacts to export")
    destination.parent.mkdir(parents=True, exist_ok=True)
    included = tuple(str(path.relative_to(root)) for path in files)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(root))
        archive.writestr(
            "export.json",
            json.dumps(
                {
                    "dataset_id": dataset_id,
                    "included_files": included,
                    "includes_snapshot": include_snapshot,
                    "exported_at": datetime.now(UTC).isoformat(),
                },
                indent=2,
            ),
        )
    return WorkspaceExport(
        dataset_id=dataset_id,
        output_path=str(destination),
        included_files=included,
        includes_snapshot=include_snapshot,
        exported_at=datetime.now(UTC),
    )


def main() -> None:
    """Export local discovery artifacts from the command line."""
    parser = argparse.ArgumentParser(description="Export Queris discovery artifacts")
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-snapshot", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(
        export_workspace(
            args.workspace,
            args.dataset_id,
            args.output,
            include_snapshot=args.include_snapshot,
            force=args.force,
        ).model_dump_json(indent=2)
    )


if __name__ == "__main__":
    main()
