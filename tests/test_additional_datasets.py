import csv
import sqlite3
import zipfile
from pathlib import Path

from queris.additional_datasets import (
    build_chinook_database,
    build_olist_database,
    build_penguins_database,
)
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


def test_build_olist_database_converts_expected_csv_archive(tmp_path: Path) -> None:
    source = tmp_path / "olist.zip"
    filenames = (
        "olist_customers_dataset.csv",
        "olist_geolocation_dataset.csv",
        "olist_order_items_dataset.csv",
        "olist_order_payments_dataset.csv",
        "olist_order_reviews_dataset.csv",
        "olist_orders_dataset.csv",
        "olist_products_dataset.csv",
        "olist_sellers_dataset.csv",
        "product_category_name_translation.csv",
    )
    files = {filename: "value\n1\n" for filename in filenames}
    files["olist_orders_dataset.csv"] = "order_id\no1\n"
    with zipfile.ZipFile(source, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)

    destination = build_olist_database(source, tmp_path / "olist.duckdb")

    with read_only_connection(destination) as database:
        tables = database.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchone()[0]
        assert tables == 9
        assert database.execute("SELECT COUNT(*) FROM olist_orders").fetchone()[0] == 1
