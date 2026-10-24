"""Bounded read-only profiling for catalog discovery and relationship hints."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from queris.database import read_only_connection
from queris.schema import introspect_schema


class ColumnProfile(BaseModel):
    """Compact statistics for one catalog column."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    data_type: str
    row_count: int = Field(ge=0)
    null_count: int = Field(ge=0)
    distinct_count: int = Field(ge=0)
    min_value: Any | None = None
    max_value: Any | None = None


class TableProfile(BaseModel):
    """Compact statistics for one catalog table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: str
    name: str
    row_count: int = Field(ge=0)
    columns: tuple[ColumnProfile, ...]


class RelationshipProfile(BaseModel):
    """A probable key relationship inferred from bounded overlap checks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    left_table: str
    left_column: str
    right_table: str
    right_column: str
    cardinality: Literal["1:1", "1:N", "N:1", "N:N"]
    coverage_percent: float = Field(ge=0, le=100)
    confidence: Literal["low", "medium", "high"]


class CatalogProfile(BaseModel):
    """Cached-ready database profile for the catalog page."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["read_only_profile"]
    tables: tuple[TableProfile, ...]
    relationships: tuple[RelationshipProfile, ...]


def profile_database(database_path: str) -> CatalogProfile:
    """Profile tables, columns, and likely relationships in read-only mode."""
    with read_only_connection(database_path) as connection:
        schema = introspect_schema(connection, sample_limit=0)
        table_profiles = tuple(_profile_table(connection, table) for table in schema.tables)
        relationships = _profile_relationships(connection, table_profiles)
    return CatalogProfile(
        source="read_only_profile",
        tables=table_profiles,
        relationships=relationships,
    )


def _profile_table(connection: Any, table: Any) -> TableProfile:
    qualified = _qualified(table.schema_name, table.name)
    row_count = int(connection.execute(f"SELECT COUNT(*) FROM {qualified}").fetchone()[0])
    columns = tuple(
        _profile_column(connection, qualified, row_count, column.name, column.data_type)
        for column in table.columns
    )
    return TableProfile(
        schema_name=table.schema_name,
        name=table.name,
        row_count=row_count,
        columns=columns,
    )


def _profile_column(
    connection: Any,
    qualified_table: str,
    row_count: int,
    name: str,
    data_type: str,
) -> ColumnProfile:
    column = _quote(name)
    values = connection.execute(
        f"""
        SELECT COUNT(*) FILTER (WHERE {column} IS NULL),
               COUNT(DISTINCT {column}), MIN({column}), MAX({column})
        FROM {qualified_table}
        """
    ).fetchone()
    return ColumnProfile(
        name=name,
        data_type=data_type,
        row_count=row_count,
        null_count=int(values[0]),
        distinct_count=int(values[1]),
        min_value=values[2],
        max_value=values[3],
    )


def _profile_relationships(
    connection: Any, tables: tuple[TableProfile, ...]
) -> tuple[RelationshipProfile, ...]:
    relationships: list[RelationshipProfile] = []
    for left_index, left in enumerate(tables):
        left_columns = {column.name: column for column in left.columns}
        for right in tables[left_index + 1 :]:
            right_columns = {column.name: column for column in right.columns}
            for column_name in sorted(left_columns.keys() & right_columns.keys()):
                if not _is_key_candidate(column_name):
                    continue
                overlap = _overlap(connection, left, right, column_name)
                if overlap is None or overlap[2] == 0:
                    continue
                left_distinct, right_distinct, matched = overlap
                coverage = matched / max(min(left_distinct, right_distinct), 1) * 100
                left_unique = left_columns[column_name].distinct_count >= left.row_count * 0.95
                right_unique = right_columns[column_name].distinct_count >= right.row_count * 0.95
                if left_unique and right_unique:
                    cardinality = "1:1"
                elif left_unique:
                    cardinality = "1:N"
                elif right_unique:
                    cardinality = "N:1"
                else:
                    cardinality = "N:N"
                confidence = (
                    "high" if coverage >= 95 and (left_unique or right_unique) else "medium"
                )
                relationships.append(
                    RelationshipProfile(
                        left_table=left.name,
                        left_column=column_name,
                        right_table=right.name,
                        right_column=column_name,
                        cardinality=cardinality,
                        coverage_percent=round(min(coverage, 100), 2),
                        confidence=confidence,
                    )
                )
    return tuple(relationships)


def _overlap(
    connection: Any, left: TableProfile, right: TableProfile, column_name: str
) -> tuple[int, int, int] | None:
    left_table = _qualified(left.schema_name, left.name)
    right_table = _qualified(right.schema_name, right.name)
    column = _quote(column_name)
    try:
        values = connection.execute(
            f"""
            WITH left_values AS (
                     SELECT DISTINCT {column} AS value
                     FROM {left_table}
                     WHERE {column} IS NOT NULL
                 ),
                 right_values AS (
                     SELECT DISTINCT {column} AS value
                     FROM {right_table}
                     WHERE {column} IS NOT NULL
                 )
            SELECT (SELECT COUNT(*) FROM left_values),
                   (SELECT COUNT(*) FROM right_values),
                   (SELECT COUNT(*) FROM left_values l INNER JOIN right_values r USING (value))
            """
        ).fetchone()
    except Exception:
        return None
    return int(values[0]), int(values[1]), int(values[2])


def _is_key_candidate(name: str) -> bool:
    lowered = name.casefold()
    return lowered.endswith("_id") or lowered in {"id", "invoice_no", "stock_code", "code"}


def _qualified(schema_name: str, table_name: str) -> str:
    return f"{_quote(schema_name)}.{_quote(table_name)}"


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
