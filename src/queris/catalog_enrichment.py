"""Resolve reviewed catalog enrichment for the active local dataset."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from queris.schema import DatabaseSchema
from queris.schema_enrichment import (
    EnrichmentReferenceIssue,
    load_schema_enrichment,
    merge_reviewed_schema_enrichment,
    validate_schema_enrichment,
)


class EnrichmentStatus(BaseModel):
    """Public enrichment state without exposing local filesystem paths."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["raw", "approved", "stale"]
    reviewed: bool
    table_count: int = Field(ge=0)
    issues: tuple[EnrichmentReferenceIssue, ...] = ()


def resolve_enrichment_path(
    database_path: str | Path, metadata_directory: str | Path
) -> Path | None:
    """Find the conventional reviewed metadata file for a dataset."""
    database = Path(database_path)
    metadata = Path(metadata_directory)
    candidates = (
        metadata / f"{database.stem}.v1.yaml",
        metadata / f"{database.stem.replace('_', '-')}.v1.yaml",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def enrich_schema(
    schema: DatabaseSchema,
    database_path: str | Path,
    metadata_directory: str | Path,
) -> tuple[DatabaseSchema, EnrichmentStatus]:
    """Merge approved metadata, failing closed when references are stale."""
    path = resolve_enrichment_path(database_path, metadata_directory)
    if path is None:
        return schema, EnrichmentStatus(status="raw", reviewed=False, table_count=0)
    enrichment = load_schema_enrichment(path)
    validation = validate_schema_enrichment(schema, enrichment)
    if not enrichment.reviewed or not validation.valid:
        return schema, EnrichmentStatus(
            status="stale" if not validation.valid else "raw",
            reviewed=enrichment.reviewed,
            table_count=len(enrichment.tables),
            issues=validation.issues,
        )
    return merge_reviewed_schema_enrichment(schema, enrichment), EnrichmentStatus(
        status="approved",
        reviewed=True,
        table_count=len(enrichment.tables),
    )
