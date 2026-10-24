"""Read-only registration checks for adding a DuckDB dataset to Queris."""

import argparse
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from queris.catalog_enrichment import EnrichmentStatus, enrich_schema
from queris.catalog_profile import profile_database
from queris.database import execute_read_only, read_only_connection
from queris.dataset_demos import get_dataset_demos
from queris.datasets import DatasetSource
from queris.enrichment_draft import draft_schema_enrichment, dump_schema_enrichment
from queris.schema import introspect_schema


class DemoValidation(BaseModel):
    """Summary of the prepared questions checked during registration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: tuple[str, ...] = ()


class DatasetWorkflowReport(BaseModel):
    """Machine-readable readiness report for one local dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    table_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    enrichment_status: EnrichmentStatus
    demo_validation: DemoValidation
    ready: bool


def validate_dataset_workflow(
    database_path: str | Path,
    *,
    metadata_directory: str | Path = "metadata",
) -> DatasetWorkflowReport:
    """Profile a dataset and execute every generated starter through read-only DuckDB."""
    database = Path(database_path)
    if database.suffix != ".duckdb":
        raise ValueError("database must be a .duckdb file")
    with read_only_connection(database) as connection:
        raw_schema = introspect_schema(connection, sample_limit=0)
        schema, enrichment = enrich_schema(raw_schema, database, metadata_directory)
        demos = get_dataset_demos(schema)
        failed: list[str] = []
        passed = 0
        for demo in demos:
            try:
                execute_read_only(connection, demo.sql)
                passed += 1
            except Exception as error:
                failed.append(f"{demo.id}: {type(error).__name__}")
    profile = profile_database(str(database))
    demo_validation = DemoValidation(total=len(demos), passed=passed, failed=tuple(failed))
    return DatasetWorkflowReport(
        dataset_id=database.name,
        table_count=len(schema.tables),
        relationship_count=len(profile.relationships),
        enrichment_status=enrichment,
        demo_validation=demo_validation,
        ready=bool(schema.tables) and not failed and len(demos) >= 50,
    )


def write_source_manifest(
    database_path: str | Path,
    output_directory: str | Path,
    *,
    name: str,
    source_url: str,
    source_name: str | None = None,
    license: str | None = None,
    force: bool = False,
) -> Path:
    """Write provenance beside reviewed metadata, never modifying the database."""
    source = DatasetSource(
        name=name,
        source_name=source_name,
        source_url=source_url,
        license=license,
    )
    output = Path(output_directory) / f"{Path(database_path).stem}.source.yaml"
    if output.exists() and not force:
        raise FileExistsError(f"source manifest already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        yaml.safe_dump(source.model_dump(exclude_none=True), sort_keys=False), encoding="utf-8"
    )
    return output


def write_enrichment_draft(
    database_path: str | Path, output: str | Path, *, force: bool = False
) -> Path:
    """Write a human-reviewable enrichment draft without touching the source database."""
    destination = Path(output)
    if destination.exists() and not force:
        raise FileExistsError(f"enrichment draft already exists: {destination}")
    with read_only_connection(database_path) as connection:
        schema = introspect_schema(connection, sample_limit=0)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        dump_schema_enrichment(draft_schema_enrichment(schema)), encoding="utf-8"
    )
    return destination


def main() -> None:
    """Run the complete dataset registration check from the command line."""
    parser = argparse.ArgumentParser(description="Validate a new DuckDB dataset for Queris")
    parser.add_argument("database", type=Path, help="Existing .duckdb path")
    parser.add_argument("--metadata-dir", type=Path, default=Path("metadata"))
    parser.add_argument("--report", type=Path, help="Optional JSON readiness report")
    parser.add_argument("--draft", type=Path, help="Optional enrichment draft output path")
    parser.add_argument("--dataset-name")
    parser.add_argument("--source-name")
    parser.add_argument("--source-url")
    parser.add_argument("--license")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source_values = (args.dataset_name, args.source_url)
    if any(source_values) and not all(source_values):
        parser.error("--dataset-name and --source-url must be supplied together")
    if all(source_values):
        write_source_manifest(
            args.database,
            args.metadata_dir,
            name=args.dataset_name,
            source_url=args.source_url,
            source_name=args.source_name,
            license=args.license,
            force=args.force,
        )
    if args.draft:
        write_enrichment_draft(args.database, args.draft, force=args.force)
    report = validate_dataset_workflow(args.database, metadata_directory=args.metadata_dir)
    payload = report.model_dump_json(indent=2)
    if args.report:
        if args.report.exists() and not args.force:
            raise FileExistsError(f"workflow report already exists: {args.report}")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    if not report.ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
