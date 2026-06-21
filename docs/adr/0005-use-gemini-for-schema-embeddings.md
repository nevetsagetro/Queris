# ADR 0005: Use Gemini for Schema Embeddings

- **Status:** Accepted
- **Date:** 2026-06-21

## Context

Phase 4 needs vector representations of live schema identifiers, reviewed business metadata, and
bounded sample summaries. The embedding boundary must remain replaceable and testable without live
credentials, consistent with the SQL-generation provider boundary from ADR 0003.

## Decision

Use the official Google Gen AI SDK with `gemini-embedding-001` as the default schema embedding
model. Allow `GEMINI_EMBEDDING_MODEL` to override the model and continue to read credentials only
from `GEMINI_API_KEY`. Send table and column documents as one ordered batch with the
`RETRIEVAL_DOCUMENT` task type.

Construct one deterministic JSON document per table and column. Include raw qualified identifiers,
types, reviewed descriptions, business terms, aliases, units, and bounded sample values where
applicable. Limit each rendered sample value before it reaches the provider. Keep the provider
behind a protocol and reject missing, empty, non-finite, or inconsistently sized vectors before
storage.

## Consequences

- Embedding inputs and their ordering are deterministic and auditable.
- Tests use offline providers and do not require Gemini credentials or network access.
- Schema samples remain untrusted text and are bounded before embedding.
- The embedding provider and model can be replaced without changing document construction or
  future vector storage.
