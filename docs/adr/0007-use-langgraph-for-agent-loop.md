# ADR 0007: Use LangGraph for the Agent Loop

- **Status:** Accepted
- **Date:** 2026-06-21

## Context

Phase 5 needs a bounded generate, validate, execute, and retry loop. Validation and database access
must remain deterministic application code: the model may propose SQL, but it must never decide
whether validation runs, bypass the retry cap, or receive a general-purpose execution tool.

The roadmap deferred a choice between the LangChain ecosystem and smolagents. Smolagents provides
a compact multi-step agent abstraction, but its API is documented as experimental and its default
`CodeAgent` emits Python actions. Its `ToolCallingAgent` avoids code actions, but still places the
general loop and memory model inside a higher-level agent abstraction than this workflow needs.

LangGraph is the LangChain ecosystem's low-level orchestration runtime. It models state, nodes, and
conditional edges explicitly; nodes can be ordinary Python functions, and LangGraph can be used
without LangChain model or tool abstractions. This matches Queris's existing provider protocols and
keeps security-critical control flow visible and testable.

## Decision

Use standalone LangGraph for the Phase 5 agent loop. Represent generation, validation, execution,
and retry preparation as explicit graph nodes over typed state. Use conditional edges for success,
retry, and exhausted-retry outcomes. Keep the existing `SQLGenerator`, schema selector, SQLGlot
validator, and read-only DuckDB adapter behind their current Queris-owned boundaries.

Do not expose arbitrary shell, Python, filesystem, extension, or database mutation tools to the
graph. Do not adopt LangChain model wrappers merely to use LangGraph. Add the `langgraph` dependency
on the first implementation branch, where its version and integration tests can be reviewed with
the runtime behavior.

## Consequences

- Retry state and transitions remain explicit, deterministic, and directly testable.
- Existing Gemini and offline fake providers remain usable without adapter churn.
- LangGraph adds a runtime dependency in Phase 5, but the broader LangChain package is unnecessary.
- Persistence, streaming, and human review can be added later without replacing the loop model.
- Smolagents remains unsuitable while Queris requires narrow tools and application-owned safety
  control flow rather than a general model-directed agent.

## References

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [smolagents agent reference](https://huggingface.co/docs/smolagents/en/reference/agents)
