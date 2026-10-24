# ADR 0013: Use an explicit live adapter mode

## Status

Accepted

## Context

Queris is snapshot-first, but some users need discovery and read-only analysis against a
current PostgreSQL database. The LLM must not receive a connection or execute SQL itself. A
live option also must not silently change the default local behavior.

## Decision

The API defaults to `QUERIS_RUNTIME_MODE=snapshot` and local DuckDB. Live mode is opt-in with
`QUERIS_RUNTIME_MODE=live` and a `QUERIS_POSTGRES_DSN` environment boundary. The PostgreSQL
adapter enforces a read-only session and bounded statement timeout; the agent receives only the
adapter's schema and executes generated SQL through the adapter after the same SQL policy check.
The API exposes `/runtime` with mode, engine, availability, and `read_only=true`, never the DSN.

Credentials are not written to manifests, prompts, structured logs, catalog responses, or
frontend state. Snapshot mode remains the reproducible path for enrichment, query intelligence,
and offline history.

## Consequences

- Local operation stays deterministic and requires no remote credentials.
- Live PostgreSQL can reuse the same generate/validate/execute flow.
- Connector-specific dialect behavior and live integration tests remain required before adding
  other engines.
- Live profiling performs bounded adapter queries and intentionally does not infer relationships
  until a connector-specific implementation is validated.
