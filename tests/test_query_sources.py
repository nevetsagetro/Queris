from pathlib import Path

from queris.database import read_only_connection
from queris.query_sources import extract_query_sources
from queris.schema import introspect_schema


def _schema(sample_database: Path):
    with read_only_connection(sample_database) as connection:
        return introspect_schema(connection, sample_limit=0)


def test_extract_query_sources_resolves_aliases_and_columns(sample_database: Path) -> None:
    sources = extract_query_sources(
        """
        SELECT r.name, SUM(i.revenue) AS revenue
        FROM regions AS r
        JOIN orders AS o USING (region_id)
        JOIN order_items AS i USING (order_id)
        GROUP BY r.name
        """,
        _schema(sample_database),
    )

    assert tuple((source.table_name, source.columns) for source in sources) == (
        ("regions", ("name", "region_id")),
        ("orders", ("region_id", "order_id")),
        ("order_items", ("revenue", "order_id")),
    )


def test_extract_query_sources_ignores_cte_aliases(sample_database: Path) -> None:
    sources = extract_query_sources(
        """
        WITH totals AS (
            SELECT product_id, SUM(revenue) AS revenue
            FROM order_items
            GROUP BY product_id
        )
        SELECT p.category, t.revenue
        FROM totals AS t
        JOIN products AS p USING (product_id)
        """,
        _schema(sample_database),
    )

    assert tuple(source.table_name for source in sources) == ("products", "order_items")
    assert sources[0].columns == ("category", "product_id")
    assert sources[1].columns == ("product_id", "revenue")


def test_extract_query_sources_records_star_for_every_table(sample_database: Path) -> None:
    [source] = extract_query_sources("SELECT * FROM orders", _schema(sample_database))

    assert source.table_name == "orders"
    assert source.columns == ("*",)
