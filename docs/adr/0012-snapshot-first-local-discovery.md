# ADR 0012: Snapshot-first local discovery

## Status

Accepted

## Context

Queris must help users understand unfamiliar databases and ask natural-language questions without
mutating source systems, leaking credentials, or creating an avoidable remote query cost. A direct
live connector would make the first discovery path dependent on network availability, permissions,
engine dialects, and production workload limits.

## Decision

Queris uses a local snapshot as the default onboarding boundary. An explicit setup/import operation
may download or copy an authorized source artifact and materialize a new DuckDB file. The runtime
opens that derived database read-only. The source artifact, derived snapshot, catalog, enrichment,
query intelligence, and cache are separate versioned artifacts linked by checksum and schema
fingerprint.

The LLM receives bounded catalog context and may propose semantic metadata or SQL. It does not receive
database credentials, unrestricted database tools, or permission authority. Every generated statement
passes the existing read-only SQL policy before execution.

Live database adapters remain an optional later mode and must implement the same read-only contract.

## Consequences

Positive:

- Discovery is reproducible, local, and inexpensive after ingestion.
- Production databases are protected from exploratory queries.
- A snapshot can be tested, reviewed, cached, and shared independently.
- Source changes can be compared through checksums and schema fingerprints.
- DuckDB provides one canonical execution boundary for common input formats.

Trade-offs:

- A snapshot can become stale and needs an explicit refresh workflow.
- Large sources require download, storage, and materialization time.
- Source-specific exporters are needed for APIs and database engines.
- Live freshness is deferred until the local workflow is reliable.
