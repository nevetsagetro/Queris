"""Interactive Streamlit demo for the safe Queris agent loop."""

from pathlib import Path

import streamlit as st

from queris.agent_loop import run_agent_loop
from queris.demo_presenter import present_success
from queris.generation import GeminiSQLGenerator
from queris.pipeline import FullSchemaSelector

st.set_page_config(page_title="Queris demo", page_icon="🔎", layout="wide")
st.title("Queris")
st.caption("Ask an analytics question. Every generated query is validated and executed read-only.")

database_path = Path(st.sidebar.text_input("DuckDB database", value="data/retail.duckdb"))
question = st.text_input(
    "Question",
    placeholder="Which product categories generated the most revenue?",
)

if st.button("Run query", type="primary", disabled=not question.strip()):
    if not database_path.is_file():
        st.error(f"Database not found: {database_path}")
    else:
        with st.spinner("Generating and validating SQL..."):
            try:
                result = run_agent_loop(
                    database_path,
                    question,
                    GeminiSQLGenerator(),
                    FullSchemaSelector(),
                )
            except Exception as error:  # Streamlit must keep the demo session alive.
                st.error(f"Query could not be completed: {error}")
            else:
                if result.status == "success":
                    presentation = present_success(result)
                    st.subheader("Generated SQL")
                    st.code(result.sql, language="sql")
                    st.subheader("Results")
                    st.dataframe(presentation.records, use_container_width=True)
                    if presentation.chart is not None:
                        st.subheader("Visualization")
                        st.bar_chart(
                            presentation.records,
                            x=presentation.chart.x,
                            y=list(presentation.chart.y),
                        )
                    st.subheader("Explanation")
                    st.write(presentation.explanation)
                elif result.status == "clarification":
                    st.info(result.clarification)
                elif result.status == "no_answer":
                    st.warning(result.no_answer)
                else:
                    st.error(result.explanation or result.error or "The query failed.")
