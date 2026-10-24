"""Deterministic demos for public datasets without the retail-specific registry."""

# SQL templates are intentionally kept readable as single statements.
# ruff: noqa: E501

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
    """Return deterministic demos for a recognized or newly registered schema."""
    table_names = {table.name for table in schema.tables}
    olist = (
        _olist_demos(schema) if {"olist_orders", "olist_order_items"}.issubset(table_names) else ()
    )
    if olist:
        return _pad_dataset_demos(schema, olist)
    penguins = _penguin_demos(schema) if "penguins" in table_names else ()
    if penguins:
        return _pad_dataset_demos(schema, penguins)
    if {"Track", "Album", "Artist"}.issubset(table_names):
        return _pad_dataset_demos(schema, ())
    return _pad_dataset_demos(schema, ()) if schema.tables else ()


def get_dataset_demo(schema: DatabaseSchema, demo_id: str | None) -> DatasetDemo | None:
    """Resolve a dataset demo only when its required schema is present."""
    if demo_id is None:
        return None
    return next((demo for demo in get_dataset_demos(schema) if demo.id == demo_id), None)


def _penguin_demos(schema: DatabaseSchema) -> tuple[DatasetDemo, ...]:
    columns = {
        column.name
        for table in schema.tables
        if table.name == "penguins"
        for column in table.columns
    }
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
    ) + _penguin_generated_demos(schema)


def _penguin_generated_demos(schema: DatabaseSchema) -> tuple[DatasetDemo, ...]:
    measures = (
        ("body_mass_g", "body mass", "average_body_mass_g"),
        ("bill_length_mm", "bill length", "average_bill_length_mm"),
        ("bill_depth_mm", "bill depth", "average_bill_depth_mm"),
        ("flipper_length_mm", "flipper length", "average_flipper_length_mm"),
    )
    dimensions = (("species", "species"), ("island", "island"), ("sex", "sex"), ("year", "year"))
    demos: list[DatasetDemo] = []
    for dimension, label in dimensions:
        for column, measure_label, alias in measures:
            demos.append(
                DatasetDemo(
                    id=f"penguins-average-{column}-by-{dimension}",
                    question=f"What is the average {measure_label} by {label}?",
                    reason=f"Compare {measure_label} across the {label} dimension.",
                    tables=("penguins",),
                    chart="line" if dimension == "year" else "bar",
                    sql=f'SELECT {dimension}, ROUND(AVG({column}), 2) AS {alias} FROM "penguins" WHERE {column} IS NOT NULL GROUP BY {dimension} ORDER BY {dimension}',
                )
            )
    for column, measure_label, _alias in measures:
        demos.extend(
            (
                DatasetDemo(
                    id=f"penguins-median-{column}",
                    question=f"What is the median {measure_label} by species?",
                    reason=f"A median is more robust than an average for {measure_label} comparisons.",
                    tables=("penguins",),
                    chart="bar",
                    sql=f'SELECT species, ROUND(QUANTILE_CONT({column}, 0.5), 2) AS median_{column} FROM "penguins" WHERE {column} IS NOT NULL GROUP BY species ORDER BY median_{column} DESC',
                ),
                DatasetDemo(
                    id=f"penguins-rank-{column}",
                    question=f"What is the {measure_label} rank within each species?",
                    reason="A window ranking compares individual observations within species.",
                    tables=("penguins",),
                    chart="table",
                    sql=f'SELECT species, island, {column}, RANK() OVER (PARTITION BY species ORDER BY {column} DESC) AS measurement_rank FROM "penguins" WHERE {column} IS NOT NULL ORDER BY species, measurement_rank LIMIT 50',
                ),
            )
        )
    for left, left_label, right, right_label in (
        ("bill_length_mm", "bill length", "bill_depth_mm", "bill depth"),
        ("bill_length_mm", "bill length", "body_mass_g", "body mass"),
        ("flipper_length_mm", "flipper length", "body_mass_g", "body mass"),
        ("bill_depth_mm", "bill depth", "body_mass_g", "body mass"),
    ):
        demos.append(
            DatasetDemo(
                id=f"penguins-correlation-{left}-{right}",
                question=f"How are {left_label} and {right_label} correlated?",
                reason="Correlation tests the relationship between two numeric measurements.",
                tables=("penguins",),
                chart="metric",
                sql=f'SELECT ROUND(CORR({left}, {right}), 3) AS correlation FROM "penguins" WHERE {left} IS NOT NULL AND {right} IS NOT NULL',
            )
        )
    return tuple(demos)


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
            tables=(
                "olist_order_reviews",
                "olist_order_items",
                "olist_products",
                "product_category_name_translation",
            ),
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


def _pad_dataset_demos(
    schema: DatabaseSchema, curated: tuple[DatasetDemo, ...], target: int = 50
) -> tuple[DatasetDemo, ...]:
    """Add tested catalog/discovery queries until every public workspace is equally deep."""
    demos = list(curated)
    existing = {demo.id for demo in demos}
    numeric_types = ("INTEGER", "BIGINT", "DOUBLE", "DECIMAL", "FLOAT", "HUGEINT")
    for table in schema.tables:
        quoted_table = _quote(table.name)
        demos.append(
            DatasetDemo(
                id=f"catalog-row-count-{table.name}",
                question=f"How many rows are in {table.name}?",
                reason="A row-count baseline validates the scale of the active table.",
                tables=(table.name,),
                chart="metric",
                sql=f"SELECT COUNT(*) AS row_count FROM {quoted_table}",
            )
        )
        for column in table.columns:
            quoted_column = _quote(column.name)
            demos.append(
                DatasetDemo(
                    id=f"catalog-distinct-{table.name}-{column.name}",
                    question=f"How many distinct {column.name} values are in {table.name}?",
                    reason="Distinct values reveal the cardinality of a business field.",
                    tables=(table.name,),
                    chart="metric",
                    sql=f"SELECT COUNT(DISTINCT {quoted_column}) AS distinct_count FROM {quoted_table}",
                )
            )
            if column.data_type.upper().split("(", 1)[0] in numeric_types:
                demos.append(
                    DatasetDemo(
                        id=f"catalog-summary-{table.name}-{column.name}",
                        question=f"What is the numeric profile of {column.name} in {table.name}?",
                        reason="A compact numeric profile exposes range and central tendency.",
                        tables=(table.name,),
                        chart="table",
                        sql=f"SELECT ROUND(MIN({quoted_column}), 2) AS minimum, ROUND(AVG({quoted_column}), 2) AS average, ROUND(MAX({quoted_column}), 2) AS maximum FROM {quoted_table}",
                    )
                )
            else:
                demos.append(
                    DatasetDemo(
                        id=f"catalog-distribution-{table.name}-{column.name}",
                        question=f"What are the most common {column.name} values in {table.name}?",
                        reason="A bounded distribution highlights the dominant categories.",
                        tables=(table.name,),
                        chart="bar",
                        sql=f"SELECT {quoted_column}, COUNT(*) AS row_count FROM {quoted_table} WHERE {quoted_column} IS NOT NULL GROUP BY {quoted_column} ORDER BY row_count DESC LIMIT 10",
                    )
                )
    for table in schema.tables:
        columns = [
            column
            for column in table.columns
            if column.data_type.upper().split("(", 1)[0] in numeric_types
        ]
        dimensions = [
            column
            for column in table.columns
            if column.data_type.upper().split("(", 1)[0] not in numeric_types
        ]
        for measure in columns:
            for dimension in dimensions[:4]:
                demos.append(
                    DatasetDemo(
                        id=f"catalog-average-{table.name}-{measure.name}-by-{dimension.name}",
                        question=f"What is the average {measure.name} by {dimension.name} in {table.name}?",
                        reason="A grouped measure connects a numeric field to a business dimension.",
                        tables=(table.name,),
                        chart="bar",
                        sql=f"SELECT {_quote(dimension.name)}, ROUND(AVG({_quote(measure.name)}), 2) AS average_value FROM {_quote(table.name)} WHERE {_quote(measure.name)} IS NOT NULL GROUP BY {_quote(dimension.name)} ORDER BY average_value DESC LIMIT 20",
                    )
                )

    demos.extend(_generic_profile_demos(schema))
    unique: list[DatasetDemo] = []
    for demo in demos:
        if demo.id not in existing:
            existing.add(demo.id)
            unique.append(demo)
        if len(curated) + len(unique) >= target:
            break
    return tuple((*curated, *unique))


def _generic_profile_demos(schema: DatabaseSchema) -> tuple[DatasetDemo, ...]:
    """Add portable quality, distribution, and window starters for an unknown schema."""
    demos: list[DatasetDemo] = []
    numeric_types = ("INTEGER", "BIGINT", "DOUBLE", "DECIMAL", "FLOAT", "HUGEINT")
    for table in schema.tables:
        table_name = _quote(table.name)
        for column in table.columns:
            name = _quote(column.name)
            identifier = f"{table.name}-{column.name}"
            demos.extend(
                (
                    DatasetDemo(
                        id=f"quality-null-{identifier}",
                        question=f"How many {column.name} values are missing in {table.name}?",
                        reason="Missingness is a first-pass data quality check for every field.",
                        tables=(table.name,),
                        chart="metric",
                        sql=f"SELECT COUNT(*) FILTER (WHERE {name} IS NULL) AS missing_count FROM {table_name}",
                    ),
                    DatasetDemo(
                        id=f"quality-present-{identifier}",
                        question=f"How complete is {column.name} in {table.name}?",
                        reason="Completeness measures how much usable data a field contains.",
                        tables=(table.name,),
                        chart="metric",
                        sql=f"SELECT ROUND(100.0 * COUNT({name}) / NULLIF(COUNT(*), 0), 2) AS completeness_percent FROM {table_name}",
                    ),
                    DatasetDemo(
                        id=f"quality-cardinality-{identifier}",
                        question=f"What is the cardinality ratio of {column.name} in {table.name}?",
                        reason="Cardinality distinguishes identifiers from repeated business dimensions.",
                        tables=(table.name,),
                        chart="metric",
                        sql=f"SELECT ROUND(1.0 * COUNT(DISTINCT {name}) / NULLIF(COUNT({name}), 0), 4) AS cardinality_ratio FROM {table_name}",
                    ),
                    DatasetDemo(
                        id=f"quality-duplicates-{identifier}",
                        question=f"How many repeated {column.name} values are in {table.name}?",
                        reason="Repeated values help distinguish identifiers from reusable dimensions.",
                        tables=(table.name,),
                        chart="metric",
                        sql=f"SELECT COUNT({name}) - COUNT(DISTINCT {name}) AS repeated_value_count FROM {table_name}",
                    ),
                    DatasetDemo(
                        id=f"distribution-top-{identifier}",
                        question=f"What are the most frequent {column.name} values in {table.name}?",
                        reason="Frequency ranking is a portable first look at any categorical field.",
                        tables=(table.name,),
                        chart="bar",
                        sql=f"SELECT {name}, COUNT(*) AS value_count FROM {table_name} WHERE {name} IS NOT NULL GROUP BY {name} ORDER BY value_count DESC LIMIT 10",
                    ),
                    DatasetDemo(
                        id=f"distribution-rare-{identifier}",
                        question=f"What are the least frequent {column.name} values in {table.name}?",
                        reason="The long tail can expose rare segments or inconsistent values.",
                        tables=(table.name,),
                        chart="bar",
                        sql=f"SELECT {name}, COUNT(*) AS value_count FROM {table_name} WHERE {name} IS NOT NULL GROUP BY {name} ORDER BY value_count LIMIT 10",
                    ),
                    DatasetDemo(
                        id=f"distribution-ascending-{identifier}",
                        question=f"What are the first ordered {column.name} values in {table.name}?",
                        reason="An ordered sample makes ranges and unexpected values visible.",
                        tables=(table.name,),
                        chart="table",
                        sql=f"SELECT DISTINCT {name} FROM {table_name} WHERE {name} IS NOT NULL ORDER BY {name} LIMIT 10",
                    ),
                    DatasetDemo(
                        id=f"distribution-descending-{identifier}",
                        question=f"What are the last ordered {column.name} values in {table.name}?",
                        reason="The upper end of an ordered field provides a complementary boundary check.",
                        tables=(table.name,),
                        chart="table",
                        sql=f"SELECT DISTINCT {name} FROM {table_name} WHERE {name} IS NOT NULL ORDER BY {name} DESC LIMIT 10",
                    ),
                )
            )
            if column.data_type.upper().split("(", 1)[0] in numeric_types:
                demos.extend(
                    (
                        DatasetDemo(
                            id=f"numeric-median-{identifier}",
                            question=f"What is the median {column.name} in {table.name}?",
                            reason="The median provides a robust center for a numeric measure.",
                            tables=(table.name,),
                            chart="metric",
                            sql=f"SELECT ROUND(MEDIAN({name}), 2) AS median_value FROM {table_name}",
                        ),
                        DatasetDemo(
                            id=f"numeric-spread-{identifier}",
                            question=f"What is the spread of {column.name} in {table.name}?",
                            reason="Standard deviation gives a compact view of numeric variation.",
                            tables=(table.name,),
                            chart="metric",
                            sql=f"SELECT ROUND(STDDEV_POP({name}), 2) AS standard_deviation FROM {table_name}",
                        ),
                        DatasetDemo(
                            id=f"numeric-quantiles-{identifier}",
                            question=f"What are the quartiles of {column.name} in {table.name}?",
                            reason="Quartiles expose skew and outliers without returning raw rows.",
                            tables=(table.name,),
                            chart="table",
                            sql=f"SELECT ROUND(QUANTILE_CONT({name}, 0.25), 2) AS p25, ROUND(QUANTILE_CONT({name}, 0.5), 2) AS p50, ROUND(QUANTILE_CONT({name}, 0.75), 2) AS p75 FROM {table_name}",
                        ),
                        DatasetDemo(
                            id=f"numeric-ascending-{identifier}",
                            question=f"What are the smallest {column.name} values in {table.name}?",
                            reason="A bounded ordered sample highlights the lower end of a measure.",
                            tables=(table.name,),
                            chart="table",
                            sql=f"SELECT {name} FROM {table_name} WHERE {name} IS NOT NULL ORDER BY {name} LIMIT 10",
                        ),
                        DatasetDemo(
                            id=f"numeric-descending-{identifier}",
                            question=f"What are the largest {column.name} values in {table.name}?",
                            reason="A bounded ordered sample highlights the upper end of a measure.",
                            tables=(table.name,),
                            chart="table",
                            sql=f"SELECT {name} FROM {table_name} WHERE {name} IS NOT NULL ORDER BY {name} DESC LIMIT 10",
                        ),
                    )
                )
            elif column.data_type.upper().startswith("VARCHAR"):
                demos.extend(
                    (
                        DatasetDemo(
                            id=f"text-length-{identifier}",
                            question=f"What is the text length profile of {column.name} in {table.name}?",
                            reason="Text length helps identify inconsistent labels and identifiers.",
                            tables=(table.name,),
                            chart="table",
                            sql=f"SELECT MIN(LENGTH({name})) AS shortest, ROUND(AVG(LENGTH({name})), 2) AS average_length, MAX(LENGTH({name})) AS longest FROM {table_name} WHERE {name} IS NOT NULL",
                        ),
                        DatasetDemo(
                            id=f"text-top-{identifier}",
                            question=f"What are the most common {column.name} values in {table.name}?",
                            reason="A bounded frequency table surfaces dominant categories.",
                            tables=(table.name,),
                            chart="bar",
                            sql=f"SELECT {name}, COUNT(*) AS value_count FROM {table_name} WHERE {name} IS NOT NULL GROUP BY {name} ORDER BY value_count DESC LIMIT 20",
                        ),
                        DatasetDemo(
                            id=f"text-rare-{identifier}",
                            question=f"Which {column.name} values are rare in {table.name}?",
                            reason="Rare categories can reveal data-quality issues or useful long-tail segments.",
                            tables=(table.name,),
                            chart="bar",
                            sql=f"SELECT {name}, COUNT(*) AS value_count FROM {table_name} WHERE {name} IS NOT NULL GROUP BY {name} ORDER BY value_count LIMIT 20",
                        ),
                    )
                )
        for limit in (5, 10, 25, 50, 100):
            demos.append(
                DatasetDemo(
                    id=f"catalog-preview-{table.name}-{limit}",
                    question=f"Show a preview of {table.name} with {limit} rows.",
                    reason="A bounded preview helps a new user understand the table shape.",
                    tables=(table.name,),
                    chart="table",
                    sql=f"SELECT * FROM {table_name} LIMIT {limit}",
                )
            )
    return tuple(demos)


def _quote(identifier: str) -> str:
    """Quote an identifier discovered from the read-only schema."""
    return '"' + identifier.replace('"', '""') + '"'
