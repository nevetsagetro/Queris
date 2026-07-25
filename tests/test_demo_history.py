from queris.agent_loop import AgentQueryResult
from queris.demo_history import format_query_source, session_query_from_result
from queris.query_sources import QuerySource


def test_session_query_records_sql_and_sources() -> None:
    source = QuerySource(schema_name="main", table_name="orders", columns=("order_id",))
    result = AgentQueryResult(
        status="success",
        question="Show order ids",
        sql="SELECT order_id FROM orders",
        columns=("order_id",),
        rows=((1,),),
        sources=(source,),
        retry_count=0,
        latency_ms=12.5,
    )

    entry = session_query_from_result(result)

    assert entry.question == "Show order ids"
    assert entry.sql == "SELECT order_id FROM orders"
    assert entry.sources == (source,)
    assert entry.retry_count == 0
    assert entry.latency_ms == 12.5
    assert entry.blocked is False
    assert format_query_source(source) == "main.orders: order_id"


def test_session_query_records_blocked_results() -> None:
    result = AgentQueryResult(
        status="failure",
        question="Delete orders",
        sql="DELETE FROM orders",
        failure_stage="validation",
        error="Forbidden SQL operation: DELETE",
        retry_count=0,
        latency_ms=7.5,
        retries_exhausted=True,
        explanation="Could not produce executable read-only SQL after 1 attempt.",
    )

    entry = session_query_from_result(result)

    assert entry.status == "failure"
    assert entry.sql == "DELETE FROM orders"
    assert entry.retry_count == 0
    assert entry.latency_ms == 7.5
    assert entry.blocked is True
