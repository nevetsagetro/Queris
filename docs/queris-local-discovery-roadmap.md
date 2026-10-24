# Queris Local Discovery Roadmap

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

## Product definition

Queris is a local, safe, and auditable intelligence layer for discovering databases and converting
natural-language questions into validated SQL. Public datasets and downloaded snapshots are input
mechanisms, not the product boundary.

The default operating model is snapshot-first:

```text
source export → local snapshot → deterministic discovery → semantic enrichment
→ validated query intelligence → read-only local execution → cache and history
```

The LLM may interpret metadata and propose SQL, but it never receives unrestricted database access,
chooses permissions, or executes a statement. The adapter validates and executes in read-only mode.

## Non-negotiable boundaries

- Runtime connections to business data are read-only.
- Snapshot creation is an explicit setup operation and writes only a new local artifact.
- Source credentials never enter prompts, SQL, logs, or frontend responses.
- Source content and sample values are untrusted data, not instructions.
- Every generated query is validated, executed, and attributable to a schema version.
- Remote or live connectors are opt-in; local snapshot mode remains the reproducible default.
- Cache and catalog metadata live outside business tables.

## Target architecture

```text
Source registry
    ↓
Acquisition and snapshot manager
    ↓
Database adapter (DuckDB first)
    ↓
Deterministic schema/profile discovery
    ↓
Reviewed semantic catalog
    ↓
LLM query intelligence and similarity retrieval
    ↓
SQL policy validation
    ↓
Read-only execution, charts, history, and cache
```

## Wave 0 — Product contract and workspace model

**Goal:** make the local discovery product explicit before adding more connectors.

- [~] Define the public CLI vocabulary: `init` and `import` are implemented; `discover`, `enrich`, `ask`, and `refresh` remain.
- [x] Define the `.queris/` workspace layout for manifests, snapshots, catalog, intelligence, and cache.
- [x] Define a versioned snapshot manifest with source URL, format, checksum, retrieval time, and schema version.
- [x] Define dataset identity independently from a local filename.
- [x] Document snapshot mode as the default and live mode as an advanced option.
- [x] Add an ADR for snapshot-first local discovery and immutable source artifacts.

**Exit criteria:** a new user can understand what Queris owns, what it downloads, what it writes, and
what the LLM can or cannot do without reading implementation details.

## Wave 1 — Snapshot acquisition and materialization

**Goal:** turn common source formats into a reproducible local DuckDB snapshot.

- [x] Implement a typed snapshot manifest contract.
- [x] Download HTTP(S) files with size limits, timeout, checksum, and refusal to overwrite by default.
- [x] Preserve the original artifact under `raw/` and keep it separate from the derived database.
- [x] Materialize Parquet and CSV into DuckDB.
- [x] Materialize ZIP archives containing CSV files into related DuckDB tables.
- [x] Materialize SQLite databases without modifying the source file.
- [x] Reject arbitrary executable or unsupported formats with an actionable error.
- [x] Register public name, source URL, license, and retrieval timestamp.
- [x] Add cleanup rules for temporary extraction directories.

**Exit criteria:** a public Parquet, CSV, ZIP, and SQLite source each produces a new local DuckDB
snapshot with a manifest and no mutation of the source artifact.

## Wave 2 — Deterministic database discovery

**Goal:** generate a trustworthy structural catalog without calling the LLM.

- [x] Introspect tables, columns, types, nullability, and bounded samples.
- [x] Calculate row counts, distinct counts, null rates, ranges, and basic distributions.
- [x] Infer probable primary/foreign-key relationships and cardinality.
- [x] Record discovery runtime, schema fingerprint, and snapshot checksum.
- [ ] Detect schema drift between two snapshots.
- [~] Expose a machine-readable catalog report and a human-readable summary.
- [ ] Add performance limits for wide and large databases.

**Exit criteria:** the same snapshot produces the same catalog fingerprint and discovery never writes to
the business database.

## Wave 3 — LLM-assisted semantic discovery

**Goal:** use the LLM where interpretation adds value, while keeping evidence and review explicit.

- [x] Build a bounded discovery prompt from schema, profiles, relationships, and safe samples.
- [x] Generate table descriptions, column meanings, aliases, units, and business terms.
- [ ] Generate ambiguity notes and candidate join explanations.
- [x] Generate a versioned enrichment draft with source evidence references.
- [x] Require human approval before activating semantic metadata.
- [ ] Reject stale references and preserve the previous approved catalog on failure.
- [x] Cache enrichment by the bounded discovery prompt hash, which changes with the schema context.

**Exit criteria:** a new snapshot can produce a useful reviewable catalog without exposing credentials,
unbounded rows, or arbitrary database tools to the LLM.

## Wave 4 — Query intelligence generation

**Goal:** create useful, tested analysis patterns before a user asks a question.

- [x] Generate 50–60 starters per sufficiently rich schema.
- [x] Cover discovery, quality, aggregation, time series, joins, CTEs, windows, cohorts, and outliers.
- [x] Include question, SQL, tables, chart type, rationale, and result metadata.
- [ ] Use similar validated questions as bounded prompt context.
- [x] Execute every generated query through the read-only validator.
- [x] Store pass/fail results and never publish failed starters as ready-to-run.
- [x] Add chart suitability confidence to each validated result.
- [~] Persist validated query intelligence by schema fingerprint.

**Exit criteria:** the frontend opens with a useful, dataset-specific discovery history and no LLM call
is required to display or rerun an already validated starter.

## Wave 5 — Local query workspace

**Goal:** make Queris useful daily for technical and non-technical users.

- [ ] Add a workspace selector for registered local snapshots.
- [ ] Display source provenance, snapshot age, schema status, and enrichment status.
- [ ] Keep demo history and real history visibly separate.
- [x] Persist query results and SQL replay cache outside business tables.
- [~] Show execution flow: discovery, retrieval, generation, validation, execution, and cache.
- [x] Present SQL with line numbers, copy/download actions, source tables, and read-only status.
- [x] Show chart recommendations only when the result shape supports them.
- [x] Add a safe export for SQL previews, catalog, profiles, and workflow artifacts.

**Exit criteria:** a user can import a snapshot, understand its structure, run a question, inspect the
SQL and sources, and reproduce the result locally without repeating LLM work.

## Wave 6 — Refresh, drift, and cost control

**Goal:** keep local intelligence current without regenerating everything.

- [~] Add explicit snapshot refresh with checksum comparison.
- [x] Compare schema identifiers and types before deciding whether intelligence is stale.
- [ ] Invalidate only catalog, queries, and cache entries affected by schema changes.
- [ ] Reuse approved enrichment when references remain valid.
- [ ] Regenerate only impacted starters and charts.
- [ ] Report LLM calls, cache hits, execution time, and materialization cost locally.
- [x] Add a dry-run refresh plan before writing any new artifact.

**Exit criteria:** refreshing an unchanged source performs no unnecessary LLM generation, and schema
changes produce an auditable impact report.

## Wave 7 — Optional live adapters

**Goal:** support current remote data only after local snapshot behavior is stable.

- [x] Define a common adapter protocol for introspection, health checks, validation, and read-only execution.
- [~] Implement PostgreSQL with a dedicated read-only role and timeout; pooling and integration tests remain.
- [ ] Add explicit live/snapshot mode to the frontend and API.
- [ ] Keep credentials in a secret manager or environment boundary, never in manifests sent to the LLM.
- [ ] Add connector-specific SQL dialect validation and integration tests.
- [ ] Evaluate BigQuery, Snowflake, and MySQL only after PostgreSQL meets the same safety contract.

**Exit criteria:** live mode is opt-in, permission-aware, auditable, and cannot weaken the snapshot
mode's safety guarantees.

## Recommended next slice

The next implementation slice is the remaining Wave 0 work plus the rest of Wave 2:

1. Add the snapshot-first ADR.
2. Add schema drift comparison and performance limits.
3. Add a human-readable discovery summary.
4. Begin bounded LLM-assisted enrichment.
5. Test one unknown Parquet schema end to end.

Do not add live PostgreSQL before this path is reproducible. The project becomes more useful first by
making any new local snapshot discoverable, explainable, and queryable with minimal cost.
