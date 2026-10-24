"""Trusted setup commands for two structurally different demo datasets."""

import argparse
import csv
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen

import duckdb

CHINOOK_URL = "https://raw.githubusercontent.com/lerocha/chinook-database/master/ChinookDatabase/DataSources/Chinook_Sqlite.sqlite"
PENGUINS_URL = (
    "https://raw.githubusercontent.com/allisonhorst/palmerpenguins/main/inst/extdata/penguins.csv"
)
OLIST_URL = "https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce"


def download_dataset(url: str, destination: str | Path) -> Path:
    """Download a trusted source into an explicitly provided ignored path."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=60) as response:  # noqa: S310 - trusted constants only
        target.write_bytes(response.read())
    return target


def build_chinook_database(source: str | Path, destination: str | Path) -> Path:
    """Convert the official Chinook SQLite fixture into a local DuckDB file."""
    source_path = Path(source)
    destination_path = _require_new_destination(destination)
    sqlite_connection = sqlite3.connect(source_path)
    duckdb_connection = duckdb.connect(str(destination_path))
    try:
        table_names = [
            row[0]
            for row in sqlite_connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        with tempfile.TemporaryDirectory(prefix="queris-chinook-") as temporary_directory:
            for table_name in table_names:
                columns = sqlite_connection.execute(
                    f'PRAGMA table_info("{_escape(table_name)}")'
                ).fetchall()
                rows = sqlite_connection.execute(
                    f'SELECT * FROM "{_escape(table_name)}"'
                ).fetchall()
                csv_path = Path(temporary_directory) / f"{table_name}.csv"
                with csv_path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    writer.writerow([row[1] for row in columns])
                    writer.writerows(rows)
                duckdb_connection.execute(
                    f'CREATE TABLE "{_escape(table_name)}" AS '
                    "SELECT * FROM read_csv_auto(?, header=true)",
                    [str(csv_path)],
                )
    finally:
        duckdb_connection.close()
        sqlite_connection.close()
    return destination_path


def build_penguins_database(source: str | Path, destination: str | Path) -> Path:
    """Convert the Palmer Penguins CSV into a local DuckDB table."""
    source_path = Path(source)
    destination_path = _require_new_destination(destination)
    with source_path.open(newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))
    duckdb_connection = duckdb.connect(str(destination_path))
    try:
        duckdb_connection.execute(
            """CREATE TABLE penguins (
                species VARCHAR, island VARCHAR, bill_length_mm DOUBLE,
                bill_depth_mm DOUBLE, flipper_length_mm DOUBLE, body_mass_g DOUBLE,
                sex VARCHAR, year INTEGER
            )"""
        )
        rows = [
            (
                record["species"],
                record["island"],
                _float(record["bill_length_mm"]),
                _float(record["bill_depth_mm"]),
                _float(record["flipper_length_mm"]),
                _float(record["body_mass_g"]),
                record["sex"] or None,
                int(record["year"]),
            )
            for record in records
        ]
        duckdb_connection.executemany("INSERT INTO penguins VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    finally:
        duckdb_connection.close()
    return destination_path


def build_olist_database(source: str | Path, destination: str | Path) -> Path:
    """Convert the public Olist CSV archive into a local DuckDB database."""
    source_path = Path(source)
    destination_path = _require_new_destination(destination)
    table_files = {
        "olist_customers_dataset.csv": "olist_customers",
        "olist_geolocation_dataset.csv": "olist_geolocation",
        "olist_order_items_dataset.csv": "olist_order_items",
        "olist_order_payments_dataset.csv": "olist_order_payments",
        "olist_order_reviews_dataset.csv": "olist_order_reviews",
        "olist_orders_dataset.csv": "olist_orders",
        "olist_products_dataset.csv": "olist_products",
        "olist_sellers_dataset.csv": "olist_sellers",
        "product_category_name_translation.csv": "product_category_name_translation",
    }
    with (
        zipfile.ZipFile(source_path) as archive,
        tempfile.TemporaryDirectory(prefix="queris-olist-") as temporary_directory,
    ):
        members = set(archive.namelist())
        if not set(table_files).issubset(members):
            raise ValueError("Olist archive is missing one or more expected CSV files")
        archive.extractall(temporary_directory, members=table_files)
        connection = duckdb.connect(str(destination_path))
        try:
            for filename, table_name in table_files.items():
                csv_path = Path(temporary_directory) / filename
                escaped_table = _escape(table_name)
                connection.execute(
                    f'CREATE TABLE "{escaped_table}" AS '
                    "SELECT * FROM read_csv_auto(?, header=true, sample_size=-1)",
                    [str(csv_path)],
                )
        finally:
            connection.close()
    return destination_path


def build_dataset(name: str, output_directory: str | Path = "data") -> Path:
    """Download and materialize one named additional dataset."""
    output = Path(output_directory)
    raw = output / "raw"
    if name == "chinook":
        source = download_dataset(CHINOOK_URL, raw / "chinook.sqlite")
        return build_chinook_database(source, output / "chinook.duckdb")
    if name == "penguins":
        source = download_dataset(PENGUINS_URL, raw / "penguins.csv")
        return build_penguins_database(source, output / "penguins.duckdb")
    if name == "olist":
        source = download_dataset(OLIST_URL, raw / "olist-brazilian-ecommerce.zip")
        return build_olist_database(source, output / "olist.duckdb")
    raise ValueError("dataset must be one of: chinook, olist, penguins")


def _require_new_destination(destination: str | Path) -> Path:
    path = Path(destination)
    if path.exists():
        raise FileExistsError(f"refusing to replace existing database: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _escape(value: str) -> str:
    return value.replace('"', '""')


def _float(value: str) -> float | None:
    return None if not value or value == "NA" else float(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an additional Queris DuckDB dataset")
    parser.add_argument("dataset", choices=("chinook", "olist", "penguins"))
    parser.add_argument("--output-directory", type=Path, default=Path("data"))
    args = parser.parse_args()
    print(build_dataset(args.dataset, args.output_directory))


if __name__ == "__main__":
    main()
