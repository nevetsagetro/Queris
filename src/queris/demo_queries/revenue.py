"""Revenue demo query builders."""


def build_revenue_query(variant: int) -> str:
    """Build one of the ten revenue questions without using an LLM."""
    queries = {
        1: """
            SELECT o.country, ROUND(SUM(i.revenue), 2) AS revenue
            FROM orders AS o JOIN order_items AS i USING (invoice_no)
            GROUP BY o.country ORDER BY revenue DESC LIMIT 10
        """,
        2: """
            SELECT i.stock_code, ROUND(SUM(i.revenue), 2) AS revenue
            FROM order_items AS i GROUP BY i.stock_code ORDER BY revenue DESC LIMIT 10
        """,
        3: """
            SELECT DATE_TRUNC('month', o.invoice_date) AS month,
                ROUND(SUM(i.revenue), 2) AS revenue
            FROM orders AS o JOIN order_items AS i USING (invoice_no)
            GROUP BY month ORDER BY month
        """,
        4: """
            SELECT o.customer_id, ROUND(SUM(i.revenue), 2) AS revenue
            FROM orders AS o JOIN order_items AS i USING (invoice_no)
            WHERE o.customer_id IS NOT NULL GROUP BY o.customer_id
            ORDER BY revenue DESC LIMIT 10
        """,
        5: """
            SELECT o.country, ROUND(SUM(i.revenue), 2) AS revenue
            FROM orders AS o JOIN order_items AS i USING (invoice_no)
            WHERE o.country = 'United Kingdom' GROUP BY o.country
        """,
        6: """
            SELECT ROUND(SUM(i.revenue), 2) AS cancelled_revenue
            FROM orders AS o JOIN order_items AS i USING (invoice_no)
            WHERE o.is_cancelled
        """,
        7: """
            SELECT o.country, ROUND(SUM(i.revenue), 2) AS revenue
            FROM orders AS o JOIN order_items AS i USING (invoice_no)
            WHERE NOT o.is_cancelled GROUP BY o.country ORDER BY revenue DESC LIMIT 10
        """,
        8: """
            WITH order_totals AS (
                SELECT invoice_no, SUM(revenue) AS revenue FROM order_items GROUP BY invoice_no
            )
            SELECT ROUND(SUM(revenue), 2) AS revenue
            FROM order_totals WHERE revenue > (SELECT MEDIAN(revenue) FROM order_totals)
        """,
        9: """
            SELECT i.stock_code, ROUND(SUM(i.revenue), 2) AS revenue
            FROM order_items AS i WHERE i.unit_price > 10
            GROUP BY i.stock_code ORDER BY revenue DESC LIMIT 10
        """,
        10: """
            SELECT o.country, ROUND(SUM(i.revenue), 2) AS revenue
            FROM orders AS o JOIN order_items AS i USING (invoice_no)
            WHERE o.invoice_date < DATE '2011-03-01'
            GROUP BY o.country ORDER BY revenue DESC LIMIT 10
        """,
    }
    return queries.get(variant, queries[1]).strip()
