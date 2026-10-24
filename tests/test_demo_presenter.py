from queris.agent_loop import AgentQueryResult
from queris.demo_presenter import build_execution_flow, present_success


def test_present_success_builds_table_chart_and_explanation() -> None:
    result = AgentQueryResult(
        status="success",
        question="Revenue by category",
        sql="SELECT category, SUM(revenue) AS revenue FROM sales GROUP BY category",
        columns=("category", "revenue"),
        rows=(("Books", 42.5), ("Games", 30.0)),
        retry_count=0,
    )

    presentation = present_success(result)

    assert presentation.records == (
        {"category": "Books", "revenue": 42.5},
        {"category": "Games", "revenue": 30.0},
    )
    assert presentation.chart is not None
    assert presentation.chart.x == "category"
    assert presentation.chart.y == ("revenue",)
    assert presentation.explanation == (
        "The query returned 2 rows across these fields: category, revenue."
    )
    assert tuple(step.status for step in presentation.execution_flow) == (
        "complete",
        "complete",
        "complete",
        "complete",
        "complete",
        "complete",
    )


def test_present_success_explains_one_scalar_result() -> None:
    result = AgentQueryResult(
        status="success",
        question="How many orders?",
        sql="SELECT COUNT(*) AS order_count FROM orders",
        columns=("order_count",),
        rows=((12,),),
        retry_count=1,
    )

    presentation = present_success(result)

    assert presentation.records == ({"_row": 1, "order_count": 12},)
    assert presentation.chart is not None
    assert presentation.chart.x == "_row"
    assert presentation.explanation == "The result is 12 for order_count."


def test_build_execution_flow_marks_validation_failure_as_blocked() -> None:
    result = AgentQueryResult(
        status="failure",
        question="Delete every order",
        sql="DELETE FROM orders",
        failure_stage="validation",
        error="Forbidden SQL operation: DELETE",
        retry_count=3,
        retries_exhausted=True,
        explanation="Could not produce executable read-only SQL after 4 attempts.",
    )

    flow = build_execution_flow(result)

    assert flow[2].detail == "initial attempt + 3 corrections."
    assert flow[3].status == "blocked"
    assert flow[4].detail == "Rejected before database execution."
    assert flow[5].status == "skipped"


def test_present_success_omits_chart_for_empty_results() -> None:
    result = AgentQueryResult(
        status="success",
        question="Missing rows",
        sql="SELECT product_id FROM products WHERE FALSE",
        columns=("product_id",),
        rows=(),
        retry_count=0,
    )

    presentation = present_success(result)

    assert presentation.records == ()
    assert presentation.chart is None
    assert presentation.explanation == (
        "The query completed successfully but returned no matching rows."
    )
