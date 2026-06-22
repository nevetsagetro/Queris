# ADR 0008: Use Versioned JSON Evaluation Sets

- **Status:** Accepted
- **Date:** 2026-06-22

## Context

Phase 6 needs 50–100 reviewed questions with reference SQL and expected results. The existing Phase 2
baseline is a JSON array containing questions and expected rows, but it has no format version,
coverage category, expected column names, or reviewed reference SQL. The expanded set must remain
easy to diff, validate offline, and consume from Python without introducing another parser.

## Decision

Store Phase 6 evaluation sets as versioned JSON documents under `evals/`. Each document declares a
numeric format version, stable dataset identifier, deterministic fixture reference, and ordered
cases. Every case includes a unique kebab-case ID, one coverage category, the natural-language
question, one read-only DuckDB reference query, expected column names, and expected rows.

Validate documents with immutable Pydantic models configured to reject unknown fields. Reject
unsupported versions, duplicate IDs, empty values, unsafe or malformed reference SQL, and expected
rows whose width differs from the expected columns. Review reference queries by executing them
against the named deterministic fixture and comparing columns plus order-insensitive result rows.
Format changes require a new version and explicit loader support.

Keep the Phase 2 baseline and Phase 5 correction cases unchanged as historical exit evaluations.
The Phase 6 set is a separate contract and may reuse questions when their new reference metadata has
been reviewed.

## Consequences

- JSON preserves the existing standard-library and Pydantic toolchain and produces focused diffs.
- Reference SQL makes intended semantics reviewable while result matching remains the accuracy
  criterion for generated SQL.
- Explicit categories make roadmap coverage measurable before running a model.
- JSON is less convenient than YAML for comments, so rationale belongs in ADRs or case-review pull
  requests rather than inside the dataset.
