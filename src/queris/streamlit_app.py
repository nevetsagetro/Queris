"""Interactive Streamlit demo for the safe Queris agent loop."""

from pathlib import Path

import streamlit as st

from queris.agent_loop import run_agent_loop
from queris.demo_history import SessionQuery, format_query_source, session_query_from_result
from queris.demo_presenter import present_success
from queris.generation import GeminiSQLGenerator
from queris.pipeline import FullSchemaSelector

st.set_page_config(page_title="Queris demo", page_icon="🔎", layout="wide")
st.title("Queris")
st.caption("Ask an analytics question. Every generated query is validated and executed read-only.")

if "query_history" not in st.session_state:
    st.session_state.query_history = []

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
                st.session_state.query_history.append(session_query_from_result(result))
                retry_metric, latency_metric, blocked_metric = st.columns(3)
                retry_metric.metric("Retries", result.retry_count)
                latency_metric.metric("Latency", f"{result.latency_ms:.1f} ms")
                blocked_metric.metric("Blocked", "Yes" if result.blocked else "No")
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

query_history: list[SessionQuery] = st.session_state.query_history
if query_history:
    st.divider()
    st.subheader("Session history")
    for entry in reversed(query_history):
        with st.expander(entry.question):
            st.write(f"Status: {entry.status}")
            st.write(f"Retries: {entry.retry_count}")
            st.write(f"Latency: {entry.latency_ms:.1f} ms")
            st.write(f"Blocked: {'Yes' if entry.blocked else 'No'}")
            if entry.sql is not None:
                st.code(entry.sql, language="sql")
                st.markdown("**Sources**")
                if entry.sources:
                    for source in entry.sources:
                        st.write(format_query_source(source))
                else:
                    st.write("No base table sources.")
