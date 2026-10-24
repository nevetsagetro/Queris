import csv
import sqlite3
from pathlib import Path

from queris.additional_datasets import build_chinook_database, build_penguins_database
from queris.database import read_only_connection


def test_build_chinook_database_converts_sqlite_fixture(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    connection = sqlite3.connect(source)
    connection.execute("CREATE TABLE artists (id INTEGER, name TEXT)")
    connection.executemany("INSERT INTO artists VALUES (?, ?)", [(1, "A"), (2, "B")])
    connection.commit()
    connection.close()

    destination = build_chinook_database(source, tmp_path / "chinook.duckdb")

    with read_only_connection(destination) as database:
        assert database.execute("SELECT COUNT(*) FROM artists").fetchone()[0] == 2


def test_build_penguins_database_converts_csv_fixture(tmp_path: Path) -> None:
    source = tmp_path / "penguins.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "species",
                "island",
                "bill_length_mm",
                "bill_depth_mm",
                "flipper_length_mm",
                "body_mass_g",
                "sex",
                "year",
            ]
        )
        writer.writerow(["Adelie", "Dream", "39.1", "18.7", "181", "3750", "male", "2007"])

    destination = build_penguins_database(source, tmp_path / "penguins.duckdb")

    with read_only_connection(destination) as database:
        assert database.execute("SELECT COUNT(*) FROM penguins").fetchone()[0] == 1
