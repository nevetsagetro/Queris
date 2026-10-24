"""Safe discovery and selection of local DuckDB datasets."""

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class DatasetInfo(BaseModel):
    """Public metadata for one selectable local DuckDB file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    size_bytes: int = Field(ge=0)
    modified_at: datetime
    active: bool


def discover_datasets(directory: str | Path, active_path: str | Path) -> tuple[DatasetInfo, ...]:
    """List DuckDB files in a trusted directory without exposing local paths."""
    root = Path(directory).expanduser().resolve()
    active = Path(active_path).expanduser().resolve()
    if not root.is_dir():
        return ()
    datasets: list[DatasetInfo] = []
    for path in sorted(root.glob("*.duckdb")):
        if not path.is_file():
            continue
        stat = path.stat()
        datasets.append(
            DatasetInfo(
                id=path.name,
                name=path.stem.replace("_", " ").title(),
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                active=path.resolve() == active,
            )
        )
    return tuple(datasets)


def select_dataset(directory: str | Path, dataset_id: str) -> Path:
    """Resolve a dataset id inside the trusted directory, rejecting traversal."""
    root = Path(directory).expanduser().resolve()
    candidate = (root / dataset_id).resolve()
    if candidate.parent != root or candidate.suffix != ".duckdb" or not candidate.is_file():
        raise ValueError("dataset must be an existing .duckdb file in the configured directory")
    return candidate
