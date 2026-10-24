"""Prepared query builders for non-revenue demo categories."""


def build_generic_query(category: str) -> str:
    """Build the stable baseline query for a demo category."""
    queries = {
        "orders": "SELECT COUNT(DISTINCT invoice_no) AS order_count FROM orders",
        "products": """
            SELECT i.stock_code, ROUND(SUM(i.revenue), 2) AS revenue
            FROM order_items AS i GROUP BY i.stock_code ORDER BY revenue DESC LIMIT 10
        """,
        "customers": """
            SELECT o.customer_id, ROUND(SUM(i.revenue), 2) AS revenue
            FROM orders AS o JOIN order_items AS i USING (invoice_no)
            WHERE o.customer_id IS NOT NULL GROUP BY o.customer_id
            ORDER BY revenue DESC LIMIT 10
        """,
        "pricing": """
            SELECT i.stock_code, ROUND(AVG(i.unit_price), 2) AS average_unit_price
            FROM order_items AS i GROUP BY i.stock_code ORDER BY average_unit_price DESC LIMIT 10
        """,
        "cancellations": """
            SELECT ROUND(100.0 * AVG(CASE WHEN is_cancelled THEN 1 ELSE 0 END), 2)
                AS cancellation_rate_percent FROM orders
        """,
        "time-series": """
            SELECT DATE_TRUNC('month', o.invoice_date) AS month,
                ROUND(SUM(i.revenue), 2) AS revenue
            FROM orders AS o JOIN order_items AS i USING (invoice_no)
            GROUP BY month ORDER BY month
        """,
        "countries": """
            SELECT o.country, COUNT(DISTINCT o.invoice_no) AS order_count
            FROM orders AS o GROUP BY o.country ORDER BY order_count DESC LIMIT 10
        """,
        "quality": """
            SELECT 'orders' AS table_name, COUNT(*) AS row_count,
                COUNT(*) FILTER (WHERE invoice_no IS NULL) AS null_invoice_no FROM orders
            UNION ALL
            SELECT 'order_items', COUNT(*), COUNT(*) FILTER (WHERE stock_code IS NULL)
            FROM order_items
        """,
        "discovery": """
            SELECT 'orders' AS table_name, COUNT(*) AS row_count FROM orders
            UNION ALL SELECT 'order_items', COUNT(*) FROM order_items
            UNION ALL SELECT 'products', COUNT(*) FROM products
            UNION ALL SELECT 'customers', COUNT(*) FROM customers
        """,
    }
    return queries.get(category, queries["discovery"]).strip()
