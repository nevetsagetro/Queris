from pathlib import Path

from queris.catalog_profile import profile_database


def test_profile_reports_columns_and_relationships(sample_database: Path) -> None:
    profile = profile_database(str(sample_database))

    assert profile.source == "read_only_profile"
    assert profile.tables
    assert all(table.row_count >= 0 for table in profile.tables)
    assert all(column.distinct_count >= 0 for table in profile.tables for column in table.columns)
