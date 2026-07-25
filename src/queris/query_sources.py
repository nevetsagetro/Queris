"""Auditable table and column sources extracted from validated SQL."""

from pydantic import BaseModel, ConfigDict
from sqlglot import exp

from queris.schema import DatabaseSchema, TableSchema
from queris.sql_validation import parse_read_only


class QuerySource(BaseModel):
    """One live base table and the columns referenced by a query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: str
    table_name: str
    columns: tuple[str, ...]


def extract_query_sources(sql: str, schema: DatabaseSchema) -> tuple[QuerySource, ...]:
    """Resolve validated SQL table and column references against the live schema."""
    statement = parse_read_only(sql)
    cte_names = {cte.alias_or_name for cte in statement.find_all(exp.CTE)}
    tables: list[TableSchema] = []
    aliases: dict[str, TableSchema] = {}

    for table_expression in statement.find_all(exp.Table):
        if not table_expression.db and table_expression.name in cte_names:
            continue
        table = _resolve_table(schema, table_expression.db, table_expression.name)
        if table is None:
            continue
        aliases[table_expression.alias_or_name] = table
        aliases[table.name] = table
        if table not in tables:
            tables.append(table)

    columns_by_table: dict[tuple[str, str], list[str]] = {
        (table.schema_name, table.name): [] for table in tables
    }
    for column_expression in statement.find_all(exp.Column):
        column_name = column_expression.name
        candidates = _column_tables(column_expression, column_name, tables, aliases)
        _record_column(columns_by_table, candidates, column_name)

    for join in statement.find_all(exp.Join):
        for identifier in join.args.get("using") or ():
            column_name = identifier.name
            candidates = tuple(
                table
                for table in tables
                if any(column.name == column_name for column in table.columns)
            )
            _record_column(columns_by_table, candidates, column_name)

    for star in statement.find_all(exp.Star):
        if not isinstance(star.parent, exp.Column):
            _record_column(columns_by_table, tuple(tables), "*")

    return tuple(
        QuerySource(
            schema_name=table.schema_name,
            table_name=table.name,
            columns=tuple(columns_by_table[(table.schema_name, table.name)]),
        )
        for table in tables
    )


def _resolve_table(
    schema: DatabaseSchema,
    schema_name: str,
    table_name: str,
) -> TableSchema | None:
    candidates = tuple(
        table
        for table in schema.tables
        if table.name == table_name and (not schema_name or table.schema_name == schema_name)
    )
    return candidates[0] if len(candidates) == 1 else None


def _column_tables(
    expression: exp.Column,
    column_name: str,
    tables: list[TableSchema],
    aliases: dict[str, TableSchema],
) -> tuple[TableSchema, ...]:
    if expression.table:
        table = aliases.get(expression.table)
        return (table,) if table is not None else ()
    if expression.is_star:
        return tuple(tables)
    return tuple(
        table for table in tables if any(column.name == column_name for column in table.columns)
    )


def _record_column(
    columns_by_table: dict[tuple[str, str], list[str]],
    tables: tuple[TableSchema, ...],
    column_name: str,
) -> None:
    for table in tables:
        columns = columns_by_table[(table.schema_name, table.name)]
        if column_name not in columns:
            columns.append(column_name)
