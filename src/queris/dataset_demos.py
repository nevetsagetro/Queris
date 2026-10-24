"""Deterministic demos for public datasets without the retail-specific registry."""

from dataclasses import dataclass
from typing import Literal

from queris.schema import DatabaseSchema


@dataclass(frozen=True)
class DatasetDemo:
    """One schema-specific, read-only demo definition."""

    id: str
    question: str
    reason: str
    tables: tuple[str, ...]
    chart: Literal["bar", "line", "metric", "table"]
    sql: str


def get_dataset_demos(schema: DatabaseSchema) -> tuple[DatasetDemo, ...]:
    """Return deterministic demos for a recognized public dataset shape."""
    table_names = {table.name for table in schema.tables}
    olist = _olist_demos(schema) if {"olist_orders", "olist_order_items"}.issubset(table_names) else ()
    if olist:
        return olist
    penguins = _penguin_demos(schema) if "penguins" in table_names else ()
    return penguins


def get_dataset_demo(schema: DatabaseSchema, demo_id: str | None) -> DatasetDemo | None:
    """Resolve a dataset demo only when its required schema is present."""
    if demo_id is None:
        return None
    return next((demo for demo in get_dataset_demos(schema) if demo.id == demo_id), None)


def _penguin_demos(schema: DatabaseSchema) -> tuple[DatasetDemo, ...]:
    columns = {column.name for table in schema.tables if table.name == "penguins" for column in table.columns}
    if not {"species", "body_mass_g", "island", "year"}.issubset(columns):
        return ()
    return (
        DatasetDemo(
            id="penguins-species-count",
            question="How many penguins are there by species?",
            reason="Species is the main categorical dimension in the active dataset.",
            tables=("penguins",),
            chart="bar",
            sql='SELECT species, COUNT(*) AS penguin_count FROM "penguins" GROUP BY species ORDER BY penguin_count DESC',
        ),
        DatasetDemo(
            id="penguins-average-mass-species",
            question="What is the average body mass by species?",
            reason="Body mass is a numeric measure that can be compared across species.",
            tables=("penguins",),
            chart="bar",
            sql='SELECT species, ROUND(AVG(body_mass_g), 1) AS average_body_mass_g FROM "penguins" WHERE body_mass_g IS NOT NULL GROUP BY species ORDER BY average_body_mass_g DESC',
        ),
        DatasetDemo(
            id="penguins-island-count",
            question="How many penguins were recorded on each island?",
            reason="Island provides a clear geographic breakdown of the observations.",
            tables=("penguins",),
            chart="bar",
            sql='SELECT island, COUNT(*) AS penguin_count FROM "penguins" GROUP BY island ORDER BY penguin_count DESC',
        ),
        DatasetDemo(
            id="penguins-year-count",
            question="How many penguins were recorded by year?",
            reason="Year provides a compact time overview of the observations.",
            tables=("penguins",),
            chart="line",
            sql='SELECT year, COUNT(*) AS penguin_count FROM "penguins" GROUP BY year ORDER BY year',
        ),
    )


def _olist_demos(schema: DatabaseSchema) -> tuple[DatasetDemo, ...]:
    tables = {table.name: {column.name for column in table.columns} for table in schema.tables}
    required = {
        "olist_orders": {"order_id", "customer_id", "order_purchase_timestamp"},
        "olist_order_items": {"order_id", "seller_id", "price"},
    }
    if not all(table in tables and columns <= tables[table] for table, columns in required.items()):
        return ()
    return (
        DatasetDemo(
            id="olist-monthly-revenue",
            question="What was total item revenue by month?",
            reason="A monthly revenue trend is the core analytical view of the Olist marketplace.",
            tables=("olist_orders", "olist_order_items"),
            chart="line",
            sql="""WITH monthly_revenue AS (
    SELECT DATE_TRUNC('month', o.order_purchase_timestamp) AS month,
           SUM(i.price) AS revenue
    FROM olist_orders AS o
    JOIN olist_order_items AS i USING (order_id)
    GROUP BY 1
)
SELECT month, ROUND(revenue, 2) AS revenue
FROM monthly_revenue
ORDER BY month""",
        ),
        DatasetDemo(
            id="olist-seller-revenue-rank",
            question="Which sellers have the highest revenue rank?",
            reason="A window function ranks sellers after aggregating their item revenue.",
            tables=("olist_order_items",),
            chart="bar",
            sql="""WITH seller_revenue AS (
    SELECT seller_id, SUM(price) AS revenue
    FROM olist_order_items
    GROUP BY seller_id
)
SELECT seller_id,
       ROUND(revenue, 2) AS revenue,
       RANK() OVER (ORDER BY revenue DESC) AS revenue_rank
FROM seller_revenue
ORDER BY revenue_rank
LIMIT 20""",
        ),
        DatasetDemo(
            id="olist-delivery-time-by-state",
            question="What is the average delivery time by customer state?",
            reason="Orders and customers combine delivery performance with customer geography.",
            tables=("olist_orders", "olist_customers"),
            chart="bar",
            sql="""SELECT c.customer_state,
       ROUND(AVG(DATE_DIFF('day', o.order_purchase_timestamp,
                           o.order_delivered_customer_date)), 1) AS average_delivery_days
FROM olist_orders AS o
JOIN olist_customers AS c USING (customer_id)
WHERE o.order_delivered_customer_date IS NOT NULL
GROUP BY c.customer_state
ORDER BY average_delivery_days DESC""",
        ),
        DatasetDemo(
            id="olist-payment-share",
            question="What share of payment value comes from each payment type?",
            reason="A CTE and window total show payment mix as a percentage of marketplace value.",
            tables=("olist_order_payments",),
            chart="bar",
            sql="""WITH payment_totals AS (
    SELECT payment_type, SUM(payment_value) AS value
    FROM olist_order_payments
    GROUP BY payment_type
), overall AS (
    SELECT SUM(value) AS total_value FROM payment_totals
)
SELECT p.payment_type,
       ROUND(p.value, 2) AS payment_value,
       ROUND(100 * p.value / NULLIF(o.total_value, 0), 2) AS share_percent
FROM payment_totals AS p
CROSS JOIN overall AS o
ORDER BY share_percent DESC""",
        ),
        DatasetDemo(
            id="olist-repeat-customers",
            question="How many customers placed more than one order?",
            reason="A customer-level CTE identifies repeat purchasing behavior.",
            tables=("olist_orders",),
            chart="metric",
            sql="""WITH customer_orders AS (
    SELECT customer_id, COUNT(DISTINCT order_id) AS order_count
    FROM olist_orders
    GROUP BY customer_id
)
SELECT COUNT(*) AS repeat_customer_count
FROM customer_orders
WHERE order_count > 1""",
        ),
        DatasetDemo(
            id="olist-review-by-category",
            question="What is the average review score by product category?",
            reason="Reviews, products, and translation tables connect satisfaction to product categories.",
            tables=("olist_order_reviews", "olist_order_items", "olist_products", "product_category_name_translation"),
            chart="bar",
            sql="""SELECT t.product_category_name_english AS category,
       ROUND(AVG(r.review_score), 2) AS average_review_score
FROM olist_order_reviews AS r
JOIN olist_order_items AS i USING (order_id)
JOIN olist_products AS p USING (product_id)
JOIN product_category_name_translation AS t
  USING (product_category_name)
GROUP BY category
ORDER BY average_review_score DESC""",
        ),
    )
