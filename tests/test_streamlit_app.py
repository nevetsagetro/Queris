from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import queris.agent_loop as agent_loop
import queris.generation as generation
from queris.agent_loop import AgentQueryResult
from queris.query_sources import QuerySource

APP_PATH = Path("src/queris/streamlit_app.py")


def test_streamlit_app_renders_safe_query_flow() -> None:
    app = AppTest.from_file(str(APP_PATH)).run()

    assert app.title[0].value == "Queris"
    assert app.sidebar.text_input[0].label == "DuckDB database"
    assert app.text_input[0].label == "Question"
    assert app.button[0].label == "Run query"


def test_streamlit_app_reports_missing_database_without_generation() -> None:
    app = AppTest.from_file(str(APP_PATH)).run()
    app.sidebar.text_input[0].set_value("data/missing.duckdb")
    app.text_input[0].set_value("How many orders are there?")
    app.button[0].click().run()

    assert app.error[0].value == "Database not found: data/missing.duckdb"


def test_streamlit_app_retains_successful_query_and_sources(
    sample_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = AgentQueryResult(
        status="success",
        question="How many orders are there?",
        sql="SELECT COUNT(*) AS order_count FROM orders",
        columns=("order_count",),
        rows=((4,),),
        sources=(QuerySource(schema_name="main", table_name="orders", columns=("*",)),),
        retry_count=1,
        latency_ms=12.5,
    )
    monkeypatch.setattr(generation, "GeminiSQLGenerator", lambda: object())
    monkeypatch.setattr(agent_loop, "run_agent_loop", lambda *args, **kwargs: result)

    app = AppTest.from_file(str(APP_PATH)).run()
    app.sidebar.text_input[0].set_value(str(sample_database))
    app.text_input[0].set_value(result.question)
    app.button[0].click().run()

    assert app.subheader[-1].value == "Session history"
    assert tuple((metric.label, metric.value) for metric in app.metric) == (
        ("Retries", "1"),
        ("Latency", "12.5 ms"),
        ("Blocked", "No"),
    )
    assert app.expander[0].label == result.question
    assert app.expander[0].code[0].value == result.sql
    assert app.expander[0].markdown[0].value == "Status: success"
    assert app.expander[0].markdown[3].value == "Blocked: No"
    assert app.expander[0].markdown[4].value == "**Sources**"
    assert app.expander[0].markdown[5].value == "main.orders: *"


def test_streamlit_app_surfaces_and_retains_blocked_status(
    sample_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = AgentQueryResult(
        status="failure",
        question="Delete every order",
        sql="DELETE FROM orders",
        failure_stage="validation",
        error="Forbidden SQL operation: DELETE",
        retry_count=3,
        latency_ms=8.25,
        retries_exhausted=True,
        explanation="Could not produce executable read-only SQL after 4 attempts.",
    )
    monkeypatch.setattr(generation, "GeminiSQLGenerator", lambda: object())
    monkeypatch.setattr(agent_loop, "run_agent_loop", lambda *args, **kwargs: result)

    app = AppTest.from_file(str(APP_PATH)).run()
    app.sidebar.text_input[0].set_value(str(sample_database))
    app.text_input[0].set_value(result.question)
    app.button[0].click().run()

    assert tuple((metric.label, metric.value) for metric in app.metric) == (
        ("Retries", "3"),
        ("Latency", "8.2 ms"),
        ("Blocked", "Yes"),
    )
    assert app.error[0].value == result.explanation
    assert app.expander[0].markdown[0].value == "Status: failure"
    assert app.expander[0].markdown[3].value == "Blocked: Yes"
