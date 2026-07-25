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
        retry_count=0,
    )
    monkeypatch.setattr(generation, "GeminiSQLGenerator", lambda: object())
    monkeypatch.setattr(agent_loop, "run_agent_loop", lambda *args, **kwargs: result)

    app = AppTest.from_file(str(APP_PATH)).run()
    app.sidebar.text_input[0].set_value(str(sample_database))
    app.text_input[0].set_value(result.question)
    app.button[0].click().run()

    assert app.subheader[-1].value == "Session history"
    assert app.expander[0].label == result.question
    assert app.expander[0].code[0].value == result.sql
    assert app.expander[0].markdown[0].value == "**Sources**"
    assert app.expander[0].markdown[1].value == "main.orders: *"
