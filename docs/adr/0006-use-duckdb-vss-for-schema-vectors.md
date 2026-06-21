# ADR 0006: Use DuckDB VSS for Schema Vectors

- **Status:** Accepted
- **Date:** 2026-06-21

## Context

Phase 0 deferred the vector-store choice between DuckDB VSS and pgvector. The MVP already uses
DuckDB and needs a small, local index of rebuildable schema documents. Adding PostgreSQL solely for
this index would introduce deployment and operational complexity before retrieval quality is known.

DuckDB documents its VSS extension and persistent HNSW indexes as experimental because custom-index
WAL recovery is incomplete. That risk is unacceptable for source analytics data but manageable for
a separate derived index that can be regenerated from live schema and reviewed metadata.

## Decision

Use DuckDB VSS for the Phase 4 local MVP. Store vectors in a dedicated DuckDB database, never in the
read-only analytics database. Use fixed-size `FLOAT[n]` arrays and a cosine HNSW index. Replace the
entire schema-vector table transactionally so re-indexing removes stale documents and a failed write
preserves the previous committed index.

Keep extension installation an explicit trusted setup action. Enable DuckDB's experimental HNSW
persistence only for the derived vector database. Store the embedding model with every document and
reject empty batches, duplicate references, and inconsistent dimensions before opening the database.

## Consequences

- The local MVP has no additional database service or credential boundary.
- The index is disposable and must be rebuilt after suspected corruption or an embedding model
  change.
- Agent-generated SQL remains unable to install, load, or mutate extensions and vector tables.
- Production adoption requires reevaluating DuckDB VSS persistence; pgvector remains the fallback if
  durable concurrent vector storage becomes necessary.
