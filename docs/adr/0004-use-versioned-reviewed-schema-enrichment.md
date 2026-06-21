# ADR 0004: Use Versioned, Reviewed Schema Enrichment

- **Status:** Accepted
- **Date:** 2026-06-21

## Context

Phase 4 needs business context that database introspection cannot provide, including descriptions,
business terminology, aliases, and units. This metadata will eventually influence schema retrieval
and generated SQL, so stale, malformed, or unreviewed content must not silently enter the active
retrieval index.

## Decision

Store enrichment as reviewable YAML documents under `metadata/`. Each document declares a numeric
format version, an explicit review flag, and table references qualified by schema name. Table and
column entries may add descriptions, business terms, and aliases; columns may also declare a unit.

Validate documents with immutable Pydantic models configured to reject unknown fields. Reject empty
entries, unsupported versions, and case-insensitive duplicate table, column, business-term, or alias
labels. Parse files with PyYAML's safe loader. A later activation step must require `reviewed: true`
and verify every reference against the live introspected schema before indexing.

## Consequences

- Metadata changes are diffable, versioned with the code, and suitable for human review.
- Draft-generation tooling can emit `reviewed: false` without making the draft active.
- Format changes require a new supported version and an explicit migration rather than silently
  changing existing documents.
- YAML and PyYAML become part of the trusted configuration boundary; enrichment text remains
  untrusted context when presented to a model.
