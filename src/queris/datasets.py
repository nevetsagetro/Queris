"""Safe discovery and selection of local DuckDB datasets."""

from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

DATASET_PROVENANCE: dict[str, dict[str, str]] = {
    "online_retail.duckdb": {
        "display_name": "UCI Online Retail",
        "source_name": "UCI Machine Learning Repository",
        "source_url": "https://archive.ics.uci.edu/static/public/352/online%2Bretail.zip",
        "license": "UCI dataset terms",
    },
    "chinook.duckdb": {
        "display_name": "Chinook Database",
        "source_name": "Chinook database project",
        "source_url": "https://raw.githubusercontent.com/lerocha/chinook-database/master/ChinookDatabase/DataSources/Chinook_Sqlite.sqlite",
        "license": "MIT",
    },
    "penguins.duckdb": {
        "display_name": "Palmer Penguins",
        "source_name": "palmerpenguins project",
        "source_url": "https://raw.githubusercontent.com/allisonhorst/palmerpenguins/main/inst/extdata/penguins.csv",
        "license": "CC0",
    },
    "olist.duckdb": {
        "display_name": "Olist Brazilian E-Commerce",
        "source_name": "Kaggle · Olist",
        "source_url": "https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce",
        "license": "Kaggle dataset terms",
    },
}


class DatasetInfo(BaseModel):
    """Public metadata for one selectable local DuckDB file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    source_name: str | None = None
    source_url: str | None = None
    license: str | None = None
    size_bytes: int = Field(ge=0)
    modified_at: datetime
    active: bool


class DatasetSource(BaseModel):
    """Public provenance registered for a locally available dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    source_name: str | None = None
    source_url: str = Field(min_length=1)
    license: str | None = None


def discover_datasets(
    directory: str | Path,
    active_path: str | Path,
    metadata_directory: str | Path | None = None,
) -> tuple[DatasetInfo, ...]:
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
        source = _source_for(path, metadata_directory)
        datasets.append(
            DatasetInfo(
                id=path.name,
                name=source.name
                if source
                else DATASET_PROVENANCE.get(path.name, {}).get(
                    "display_name", path.stem.replace("_", " ").title()
                ),
                source_name=(
                    source.source_name
                    if source
                    else DATASET_PROVENANCE.get(path.name, {}).get("source_name")
                ),
                source_url=(
                    source.source_url
                    if source
                    else DATASET_PROVENANCE.get(path.name, {}).get("source_url")
                ),
                license=source.license
                if source
                else DATASET_PROVENANCE.get(path.name, {}).get("license"),
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                active=path.resolve() == active,
            )
        )
    return tuple(datasets)


def _source_for(path: Path, metadata_directory: str | Path | None) -> DatasetSource | None:
    """Load an optional source manifest, failing closed on invalid metadata."""
    if metadata_directory is None:
        return None
    manifest = Path(metadata_directory) / f"{path.stem}.source.yaml"
    if not manifest.is_file():
        return None
    try:
        document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        return DatasetSource.model_validate(document)
    except (OSError, yaml.YAMLError, ValueError):
        return None


def select_dataset(directory: str | Path, dataset_id: str) -> Path:
    """Resolve a dataset id inside the trusted directory, rejecting traversal."""
    root = Path(directory).expanduser().resolve()
    candidate = (root / dataset_id).resolve()
    if candidate.parent != root or candidate.suffix != ".duckdb" or not candidate.is_file():
        raise ValueError("dataset must be an existing .duckdb file in the configured directory")
    return candidate
