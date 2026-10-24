from queris.chart_recommender import recommend_chart


def test_temporal_result_recommends_line_chart() -> None:
    recommendation = recommend_chart(
        ("month", "revenue"),
        (("2024-01", 100), ("2024-02", 120)),
    )

    assert recommendation.chart == "line"
    assert recommendation.x_field == "month"
    assert recommendation.y_field == "revenue"


def test_single_numeric_result_recommends_metric() -> None:
    recommendation = recommend_chart(("order_count",), ((42,),))

    assert recommendation.chart == "metric"


def test_categorical_numeric_result_recommends_bar() -> None:
    recommendation = recommend_chart(("country", "revenue"), (("ES", 20), ("FR", 30)))

    assert recommendation.chart == "bar"
