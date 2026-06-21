"""Versioned, human-reviewed metadata for enriching database schemas."""

from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)

from queris.schema import ColumnSchema, DatabaseSchema, TableSchema

CleanString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SemanticMetadata(BaseModel):
    """Optional language used to explain one schema object."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    description: CleanString | None = None
    business_terms: tuple[CleanString, ...] = ()
    aliases: tuple[CleanString, ...] = ()

    @field_validator("business_terms", "aliases")
    @classmethod
    def require_unique_labels(cls, labels: tuple[str, ...]) -> tuple[str, ...]:
        normalized = [label.casefold() for label in labels]
        if len(normalized) != len(set(normalized)):
            raise ValueError("labels must be unique ignoring case")
        return labels

    def has_metadata(self) -> bool:
        """Return whether at least one semantic field is populated."""
        return bool(self.description or self.business_terms or self.aliases)


class ColumnEnrichment(SemanticMetadata):
    """Reviewed semantic metadata for one database column."""

    name: CleanString
    unit: CleanString | None = None

    @model_validator(mode="after")
    def require_metadata(self) -> Self:
        if not self.has_metadata() and self.unit is None:
            raise ValueError("column enrichment must define semantic metadata or a unit")
        return self


class TableEnrichment(SemanticMetadata):
    """Reviewed semantic metadata for one database table and selected columns."""

    schema_name: CleanString
    name: CleanString
    columns: tuple[ColumnEnrichment, ...] = ()

    @model_validator(mode="after")
    def require_metadata_and_unique_columns(self) -> Self:
        if not self.has_metadata() and not self.columns:
            raise ValueError("table enrichment must define semantic metadata or columns")
        _require_unique_references(
            (column.name for column in self.columns),
            "column references",
        )
        return self


class SchemaEnrichment(BaseModel):
    """Versioned schema-enrichment document ready for explicit review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    reviewed: StrictBool
    tables: tuple[TableEnrichment, ...]

    @field_validator("version", mode="before")
    @classmethod
    def require_integer_version(cls, version: object) -> object:
        if type(version) is not int:
            raise ValueError("version must be an integer")
        return version

    @model_validator(mode="after")
    def require_tables_with_unique_references(self) -> Self:
        if not self.tables:
            raise ValueError("schema enrichment must contain at least one table")
        _require_unique_references(
            (f"{table.schema_name}.{table.name}" for table in self.tables),
            "table references",
        )
        return self


def load_schema_enrichment(path: str | Path) -> SchemaEnrichment:
    """Load one YAML enrichment document using the safe YAML loader."""
    try:
        raw_enrichment = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError("schema enrichment YAML could not be parsed") from error
    return SchemaEnrichment.model_validate(raw_enrichment)


def merge_schema_enrichment(
    schema: DatabaseSchema,
    enrichment: SchemaEnrichment | None,
) -> DatabaseSchema:
    """Merge reviewed, current semantic metadata into an introspected schema."""
    if enrichment is None or not enrichment.reviewed:
        return schema

    tables_by_reference = {(table.schema_name, table.name): table for table in schema.tables}
    for table_metadata in enrichment.tables:
        table = tables_by_reference.get((table_metadata.schema_name, table_metadata.name))
        if table is None:
            return schema
        column_names = {column.name for column in table.columns}
        if any(column.name not in column_names for column in table_metadata.columns):
            return schema

    enrichment_by_reference = {
        (table.schema_name, table.name): table for table in enrichment.tables
    }
    return DatabaseSchema(
        tables=tuple(
            _merge_table(
                table,
                enrichment_by_reference.get((table.schema_name, table.name)),
            )
            for table in schema.tables
        )
    )


def _merge_table(
    table: TableSchema,
    metadata: TableEnrichment | None,
) -> TableSchema:
    if metadata is None:
        return table

    columns_by_name = {column.name: column for column in metadata.columns}
    return table.model_copy(
        update={
            "description": metadata.description,
            "business_terms": metadata.business_terms,
            "aliases": metadata.aliases,
            "columns": tuple(
                _merge_column(column, columns_by_name.get(column.name)) for column in table.columns
            ),
        }
    )


def _merge_column(
    column: ColumnSchema,
    metadata: ColumnEnrichment | None,
) -> ColumnSchema:
    if metadata is None:
        return column
    return column.model_copy(
        update={
            "description": metadata.description,
            "business_terms": metadata.business_terms,
            "aliases": metadata.aliases,
            "unit": metadata.unit,
        }
    )


def _require_unique_references(references: Iterable[str], label: str) -> None:
    normalized = [str(reference).casefold() for reference in references]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must be unique ignoring case")
