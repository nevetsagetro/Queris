import sys
from pathlib import Path

import pytest

from queris.database import read_only_connection
from queris.schema import introspect_schema
from queris.schema_enrichment import load_schema_enrichment, validate_schema_enrichment
from queris.wide_schema import (
    WIDE_TABLE_NAMES,
    create_wide_schema_database,
    load_retrieval_labels,
    main,
)

LABELS_PATH = Path("evals/wide_schema_retrieval.json")
ENRICHMENT_PATH = Path("metadata/wide-schema.v1.yaml")


@pytest.fixture
def wide_schema_database(tmp_path: Path) -> Path:
    return create_wide_schema_database(tmp_path / "wide.duckdb")


def test_create_wide_schema_database_has_ambiguous_columns_on_32_tables(
    wide_schema_database: Path,
) -> None:
    with read_only_connection(wide_schema_database) as connection:
        schema = introspect_schema(connection, sample_limit=0)

    assert len(schema.tables) == 32
    assert {table.name for table in schema.tables} == set(WIDE_TABLE_NAMES)
    assert all(
        {"amt", "qty", "flg_x"}.issubset(column.name for column in table.columns)
        for table in schema.tables
    )


def test_wide_schema_rows_are_deterministic(wide_schema_database: Path) -> None:
    with read_only_connection(wide_schema_database) as connection:
        rows = connection.execute(
            """
            SELECT row_id, entity_id, amt, qty, flg_x, event_date
            FROM accounts_receivable
            ORDER BY row_id
            """
        ).fetchall()

    assert [tuple(map(str, row)) for row in rows] == [
        ("1", "101", "10.25", "1", "False", "2026-01-01"),
        ("2", "102", "15.75", "2", "True", "2026-01-15"),
    ]


def test_wide_schema_retrieval_labels_reference_live_ambiguous_columns(
    wide_schema_database: Path,
) -> None:
    labels = load_retrieval_labels(LABELS_PATH)
    with read_only_connection(wide_schema_database) as connection:
        schema = introspect_schema(connection, sample_limit=0)
    live_columns = {
        (table.schema_name, table.name, column.name)
        for table in schema.tables
        for column in table.columns
    }
    references = {
        (reference.schema_name, reference.table_name, reference.column_name)
        for case in labels.cases
        for reference in case.relevant_columns
    }

    assert len(labels.cases) == 10
    assert references <= live_columns
    assert {reference[2] for reference in references} == {"amt", "qty", "flg_x"}


def test_wide_schema_reviewed_enrichment_matches_live_schema(
    wide_schema_database: Path,
) -> None:
    enrichment = load_schema_enrichment(ENRICHMENT_PATH)
    with read_only_connection(wide_schema_database) as connection:
        schema = introspect_schema(connection, sample_limit=0)

    validation = validate_schema_enrichment(schema, enrichment)

    assert enrichment.reviewed is True
    assert validation.valid is True


def test_create_wide_schema_database_refuses_to_replace_existing(
    wide_schema_database: Path,
) -> None:
    with pytest.raises(FileExistsError, match="Refusing"):
        create_wide_schema_database(wide_schema_database)


def test_wide_schema_cli_prints_created_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "wide.duckdb"
    monkeypatch.setattr(sys, "argv", ["queris-wide-data", str(database)])

    main()

    assert capsys.readouterr().out.strip() == str(database)
    assert database.is_file()
