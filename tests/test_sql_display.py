from queris.sql_display import format_sql_for_display


def test_format_sql_for_display_uses_conventional_clause_indentation() -> None:
    formatted = format_sql_for_display(
        "WITH monthly AS (SELECT DATE_TRUNC('month', order_date) AS month, "
        "SUM(revenue) AS revenue FROM orders GROUP BY 1) "
        "SELECT month, revenue FROM monthly ORDER BY month"
    )

    assert "WITH monthly AS (" in formatted
    assert "\n  SELECT" in formatted
    assert "\n  FROM orders" in formatted
    assert "\n  GROUP BY" in formatted
    assert "\nORDER BY" in formatted


def test_format_sql_for_display_falls_back_to_original_sql() -> None:
    sql = "SELECT 'unterminated"

    assert format_sql_for_display(sql) == sql
