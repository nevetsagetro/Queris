"""Trusted setup utility for the deterministic retail sample database."""

import argparse
from pathlib import Path

import duckdb


def create_sample_database(database_path: str | Path) -> Path:
    """Create the retail fixture without replacing an existing database."""
    path = Path(database_path)
    if path.exists():
        raise FileExistsError(f"Refusing to replace existing path: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(database=str(path))
    try:
        _create_schema(connection)
        _load_rows(connection)
    except Exception:
        connection.close()
        path.unlink(missing_ok=True)
        raise
    else:
        connection.close()
    return path


def _create_schema(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE TABLE regions (
            region_id INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL UNIQUE
        );
        CREATE TABLE categories (
            category_id INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL UNIQUE
        );
        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            category_id INTEGER NOT NULL REFERENCES categories(category_id),
            name VARCHAR NOT NULL
        );
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            order_date DATE NOT NULL,
            region_id INTEGER NOT NULL REFERENCES regions(region_id)
        );
        CREATE TABLE order_items (
            order_id INTEGER NOT NULL REFERENCES orders(order_id),
            product_id INTEGER NOT NULL REFERENCES products(product_id),
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            revenue DECIMAL(12, 2) NOT NULL,
            cost DECIMAL(12, 2) NOT NULL,
            PRIMARY KEY (order_id, product_id)
        );
        """
    )


def _load_rows(connection: duckdb.DuckDBPyConnection) -> None:
    connection.executemany(
        "INSERT INTO regions VALUES (?, ?)",
        [(1, "North"), (2, "South"), (3, "West")],
    )
    connection.executemany(
        "INSERT INTO categories VALUES (?, ?)",
        [(1, "Office"), (2, "Technology"), (3, "Furniture")],
    )
    connection.executemany(
        "INSERT INTO products VALUES (?, ?, ?)",
        [
            (1, 1, "Notebook"),
            (2, 2, "Keyboard"),
            (3, 3, "Desk"),
        ],
    )
    connection.executemany(
        "INSERT INTO orders VALUES (?, ?, ?)",
        [
            (1, "2026-01-15", 1),
            (2, "2026-02-10", 2),
            (3, "2026-04-05", 3),
            (4, "2026-04-20", 1),
        ],
    )
    connection.executemany(
        "INSERT INTO order_items VALUES (?, ?, ?, ?, ?)",
        [
            (1, 1, 4, "40.00", "22.00"),
            (1, 2, 1, "70.00", "50.00"),
            (2, 3, 1, "200.00", "220.00"),
            (3, 2, 2, "130.00", "95.00"),
            (4, 1, 3, "28.00", "30.00"),
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the Queris retail sample database")
    parser.add_argument("database", type=Path, help="Output .duckdb path")
    args = parser.parse_args()
    created_path = create_sample_database(args.database)
    print(created_path)


if __name__ == "__main__":
    main()
