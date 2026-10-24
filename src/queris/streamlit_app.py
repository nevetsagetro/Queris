"""Interactive Streamlit demo for the safe Queris agent loop."""

from pathlib import Path

import streamlit as st

from queris.agent_loop import AgentQueryResult, run_agent_loop
from queris.demo_cache import cache_result, cached_result, load_schema_catalog
from queris.demo_history import SessionQuery, format_query_source, session_query_from_result
from queris.demo_presenter import (
    DemoPresentation,
    ExecutionStep,
    build_execution_flow,
    present_success,
)
from queris.generation import GeminiSQLGenerator
from queris.pipeline import FullSchemaSelector


def _render_execution_flow(presentation: DemoPresentation) -> None:
    """Render the successful path as a compact, readable pipeline."""
    _render_steps(presentation.execution_flow)


def _render_execution_flow_for_result(result: AgentQueryResult) -> None:
    """Render a terminal non-success path using the same visual language."""
    _render_steps(build_execution_flow(result))


def _render_steps(steps: tuple[ExecutionStep, ...]) -> None:
    st.subheader("Execution flow")
    items = []
    for index, step in enumerate(steps):
        icon = {"complete": "✓", "blocked": "!", "failed": "×", "skipped": "–"}[step.status]
        items.append(
            f'<div class="flow-step {step.status}"><div class="flow-label">'
            f"{icon} {step.label}</div>"
            f'<div class="flow-detail">{step.detail}</div></div>'
        )
        if index < len(steps) - 1:
            items.append('<div class="arrow">→</div>')
    st.markdown(f'<div class="flow">{"".join(items)}</div>', unsafe_allow_html=True)


st.set_page_config(page_title="Queris demo", page_icon="🔎", layout="wide")
st.title("Queris")
st.caption("SAFE ANALYTICS · transparent, read-only answers")
st.markdown(
    """
    <style>
    .hero { padding: 1.3rem 1.5rem; border: none; border-radius: 16px;
            background: linear-gradient(135deg, #102a43 0%, #1f4e79 100%);
            color: #ffffff; margin-bottom: 1rem; }
    .hero h1 { margin: 0; letter-spacing: -0.04em; color: #ffffff; }
    .hero p { margin: .45rem 0 0; color: #e6f0fa; }
    .flow { display: flex; gap: .45rem; align-items: stretch; overflow-x: auto;
            padding: .2rem 0 .7rem; }
    .flow-step { min-width: 145px; flex: 1; padding: .75rem; border-radius: 12px;
                 border: 1px solid #9fb3c8; background: #ffffff; color: #102a43; }
    .flow-step.complete { border-top: 5px solid #16855b; }
    .flow-step.blocked { border-top: 5px solid #b77900; background: #fff8e6; }
    .flow-step.failed { border-top: 5px solid #b42318; background: #fff1f0; }
    .flow-step.skipped { border-top: 5px solid #52606d; background: #f0f4f8; color: #334e68; }
    .flow-label { font-weight: 800; font-size: .86rem; }
    .flow-detail { color: #334e68; font-size: .76rem; margin-top: .3rem; }
    .arrow { align-self: center; color: #486581; font-size: 1.25rem; font-weight: 800; }
    </style>
    <div class="hero">
      <p>Ask a business question and watch it move through schema selection, SQL safety checks,
      and read-only execution.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if "query_history" not in st.session_state:
    st.session_state.query_history = []
if "query_cache" not in st.session_state:
    st.session_state.query_cache = {}
if "schema_cache" not in st.session_state:
    st.session_state.schema_cache = {}

default_database = Path("data/online_retail.duckdb")
if not default_database.is_file():
    default_database = Path("data/retail.duckdb")
database_path = Path(st.sidebar.text_input("DuckDB database", value=str(default_database)))
st.sidebar.markdown("### Try an analysis")
st.sidebar.caption("The question box is where you can ask Queris to analyze the database.")
st.sidebar.info(
    "Examples:\n\n"
    "• What is the average product price by category?\n\n"
    "• Which products have the highest unit price?\n\n"
    "• How has average order value changed by month?"
)
if st.sidebar.button("Clear saved analyses"):
    st.session_state.query_cache.clear()
    st.session_state.schema_cache.clear()
    st.session_state.query_history.clear()
    st.rerun()
ask_tab, catalog_tab, history_tab = st.tabs(["Ask", "Data catalog", "History"])

with ask_tab:
    question = st.text_input(
        "Question",
        placeholder="Which product categories generated the most revenue?",
        help=(
            "Try a question about the retail dataset. Mutations and unsafe SQL are blocked "
            "before execution."
        ),
    )

    if st.button("Run query", type="primary", disabled=not question.strip()):
        if not database_path.is_file():
            st.error(f"Database not found: {database_path}")
        else:
            cached = cached_result(st.session_state.query_cache, database_path, question)
            result: AgentQueryResult | None = None
            if cached is not None:
                result = cached
                st.success("Cache hit · reused this analysis without calling the model again.")
                st.caption(
                    "Session cache is invalidated automatically when the DuckDB file changes."
                )
            else:
                with st.spinner("Generating and validating SQL..."):
                    execution_status = st.status("Sending question to Queris...", expanded=True)

                    def show_progress(message: str) -> None:
                        execution_status.update(label=message, state="running", expanded=True)
                        execution_status.write(message)

                    try:
                        schema = load_schema_catalog(
                            st.session_state.schema_cache,
                            database_path,
                        )
                        result = run_agent_loop(
                            database_path,
                            question,
                            GeminiSQLGenerator(),
                            FullSchemaSelector(),
                            progress_callback=show_progress,
                            schema_override=schema,
                        )
                    except Exception as error:  # Streamlit must keep the demo session alive.
                        execution_status.update(label="Query failed", state="error", expanded=True)
                        st.error(f"Query could not be completed: {error}")
                    else:
                        cache_result(st.session_state.query_cache, database_path, question, result)
                        execution_status.update(
                            label=(
                                "Query completed" if result.status == "success" else "Query stopped"
                            ),
                            state=("complete" if result.status == "success" else "error"),
                            expanded=False,
                        )
            if result is not None:
                if cached is None:
                    st.session_state.query_history.append(session_query_from_result(result))
                retry_metric, latency_metric, blocked_metric = st.columns(3)
                retry_metric.metric("Retries", result.retry_count)
                latency_metric.metric("Latency", f"{result.latency_ms:.1f} ms")
                blocked_metric.metric("Blocked", "Yes" if result.blocked else "No")
                if result.status == "success":
                    presentation = present_success(result)
                    _render_execution_flow(presentation)
                    st.subheader("Answer")
                    st.write(presentation.explanation)
                    result_tab, sql_tab, sources_tab = st.tabs(["Results", "SQL", "Sources"])
                    with result_tab:
                        st.dataframe(presentation.records, width="stretch")
                        if presentation.chart is not None:
                            st.caption("Automatic visualization")
                            st.bar_chart(
                                presentation.records,
                                x=presentation.chart.x,
                                y=list(presentation.chart.y),
                            )
                    with sql_tab:
                        st.code(result.sql, language="sql")
                    with sources_tab:
                        if result.sources:
                            for source in result.sources:
                                st.write(format_query_source(source))
                        else:
                            st.write("No base table sources.")
                elif result.status == "clarification":
                    _render_execution_flow_for_result(result)
                    st.info(result.clarification)
                elif result.status == "no_answer":
                    _render_execution_flow_for_result(result)
                    st.warning(result.no_answer)
                else:
                    _render_execution_flow_for_result(result)
                    st.error(result.explanation or result.error or "The query failed.")

with catalog_tab:
    st.subheader("Data catalog")
    if not database_path.is_file():
        st.error(f"Database not found: {database_path}")
    else:
        try:
            catalog = load_schema_catalog(st.session_state.schema_cache, database_path)
        except Exception as error:
            st.error(f"Catalog could not be loaded: {error}")
        else:
            st.caption(
                f"{len(catalog.tables)} tables · cached in this session · "
                "refreshed when the database changes"
            )
            table_names = [f"{table.schema_name}.{table.name}" for table in catalog.tables]
            selected_name = st.selectbox("Table", table_names)
            selected_table = next(
                table
                for table in catalog.tables
                if f"{table.schema_name}.{table.name}" == selected_name
            )
            st.write(selected_table.description or "No business description available yet.")
            st.dataframe(
                [
                    {
                        "Column": column.name,
                        "Type": column.data_type,
                        "Nullable": column.nullable,
                        "Examples": ", ".join(str(value) for value in column.sample_values),
                    }
                    for column in selected_table.columns
                ],
                width="stretch",
                hide_index=True,
            )

with history_tab:
    query_history: list[SessionQuery] = st.session_state.query_history
    st.subheader("Session history")
    if not query_history:
        st.info("Your saved analyses will appear here after the first question.")
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
