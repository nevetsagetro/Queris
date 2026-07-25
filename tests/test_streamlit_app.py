from pathlib import Path

from streamlit.testing.v1 import AppTest


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
