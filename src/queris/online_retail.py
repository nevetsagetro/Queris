"""Download and normalize the licensed UCI Online Retail dataset."""

import argparse
import urllib.request
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile

import duckdb

UCI_DOWNLOAD_URL = "https://archive.ics.uci.edu/static/public/352/online%2Bretail.zip"
DEFAULT_RAW_DIR = Path("data/raw")
DEFAULT_XLSX_NAME = "Online Retail.xlsx"
DEFAULT_ARCHIVE_NAME = "online-retail.zip"
DEFAULT_EXTENSION_DIR = DEFAULT_RAW_DIR / ".duckdb-extensions"
EXPECTED_HEADERS = (
    "InvoiceNo",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
    "CustomerID",
    "Country",
)


def download_online_retail(
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    *,
    url: str = UCI_DOWNLOAD_URL,
) -> Path:
    """Download and extract the UCI workbook, reusing an existing local copy."""
    output_dir = Path(raw_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    workbook_path = output_dir / DEFAULT_XLSX_NAME
    if workbook_path.exists():
        return workbook_path

    archive_path = output_dir / DEFAULT_ARCHIVE_NAME
    if not archive_path.exists():
        with NamedTemporaryFile(dir=output_dir, suffix=".zip", delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            urllib.request.urlretrieve(url, temporary_path)
            temporary_path.replace(archive_path)
        finally:
            temporary_path.unlink(missing_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        member = next(
            (
                name
                for name in archive.namelist()
                if name.casefold() == DEFAULT_XLSX_NAME.casefold()
            ),
            None,
        )
        if member is None:
            raise ValueError(f"downloaded archive does not contain {DEFAULT_XLSX_NAME}")
        with archive.open(member) as source, workbook_path.open("wb") as target:
            target.write(source.read())
    return workbook_path


def create_online_retail_database(
    workbook_path: str | Path,
    database_path: str | Path,
    *,
    extension_dir: str | Path = DEFAULT_EXTENSION_DIR,
) -> Path:
    """Create a normalized DuckDB database from an extracted UCI workbook."""
    source_path = Path(workbook_path)
    output_path = Path(database_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"workbook not found: {source_path}")
    if output_path.exists():
        raise FileExistsError(f"refusing to replace existing path: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    extension_path = Path(extension_dir)
    extension_path.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(
        database=str(output_path),
        config={"extension_directory": str(extension_path.resolve())},
    )
    try:
        _load_raw_table(connection, source_path)
        _create_normalized_tables(connection)
    except Exception:
        connection.close()
        output_path.unlink(missing_ok=True)
        raise
    else:
        connection.close()
    return output_path


def build_online_retail_database(
    database_path: str | Path,
    *,
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    url: str = UCI_DOWNLOAD_URL,
    extension_dir: str | Path = DEFAULT_EXTENSION_DIR,
) -> Path:
    """Download the source when necessary and build a local normalized database."""
    workbook_path = download_online_retail(raw_dir, url=url)
    return create_online_retail_database(
        workbook_path,
        database_path,
        extension_dir=extension_dir,
    )


def _load_raw_table(
    connection: duckdb.DuckDBPyConnection,
    workbook_path: Path,
) -> None:
    try:
        connection.execute("LOAD excel")
    except duckdb.Error:
        connection.execute("INSTALL excel")
        connection.execute("LOAD excel")
    connection.execute(
        """
        CREATE TABLE _online_retail_raw AS
        SELECT
            "InvoiceNo" AS invoice_no,
            "StockCode" AS stock_code,
            NULLIF(trim("Description"), '') AS description,
            try_cast("Quantity" AS INTEGER) AS quantity,
            TIMESTAMP '1899-12-30'
                + try_cast("InvoiceDate" AS DOUBLE) * INTERVAL '1 day' AS invoice_date,
            try_cast("UnitPrice" AS DECIMAL(12, 4)) AS unit_price,
            try_cast("CustomerID" AS BIGINT) AS customer_id,
            NULLIF(trim("Country"), '') AS country
        FROM read_xlsx(?, all_varchar=true)
        """,
        [str(workbook_path)],
    )


def _create_normalized_tables(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE TABLE customers AS
        SELECT DISTINCT customer_id, country
        FROM _online_retail_raw
        WHERE customer_id IS NOT NULL;

        CREATE TABLE products AS
        SELECT stock_code, max(description) AS description
        FROM _online_retail_raw
        GROUP BY stock_code;

        CREATE TABLE orders AS
        SELECT
            invoice_no,
            min(invoice_date) AS invoice_date,
            max(customer_id) AS customer_id,
            max(country) AS country,
            starts_with(upper(invoice_no), 'C') AS is_cancelled
        FROM _online_retail_raw
        GROUP BY invoice_no;

        CREATE TABLE order_items AS
        SELECT
            invoice_no,
            stock_code,
            sum(quantity)::INTEGER AS quantity,
            avg(unit_price)::DECIMAL(12, 4) AS unit_price,
            sum(quantity * unit_price)::DECIMAL(14, 4) AS revenue
        FROM _online_retail_raw
        GROUP BY invoice_no, stock_code;

        DROP TABLE _online_retail_raw;
        """
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download and build the UCI Online Retail database"
    )
    parser.add_argument("database", type=Path, help="Output .duckdb path")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--extension-dir", type=Path, default=DEFAULT_EXTENSION_DIR)
    parser.add_argument("--url", default=UCI_DOWNLOAD_URL, help=argparse.SUPPRESS)
    args = parser.parse_args()
    created_path = build_online_retail_database(
        args.database,
        raw_dir=args.raw_dir,
        url=args.url,
        extension_dir=args.extension_dir,
    )
    print(created_path)


if __name__ == "__main__":
    main()
