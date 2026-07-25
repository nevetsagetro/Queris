# ADR 0010: Use Versioned Adversarial Evaluation Cases

- **Status:** Accepted
- **Date:** 2026-06-22

## Context

Phase 7 must prove that destructive natural-language intent cannot cross the application-owned SQL
safety boundary. A live model refusal is insufficient: provider behavior can change, and a model may
emit unsafe SQL despite prompt instructions. The test must be deterministic, auditable, and exercise
the same validation graph used at runtime.

## Decision

Store reviewed Phase 7 cases as a versioned JSON document under `evals/`. Each case contains a stable
ID, natural-language question, worst-case generated SQL attempt, and explicit
`blocked-before-execution` expectation. Prompt-injection cases also identify the source table,
column, and exact untrusted sample value. Validate the document with immutable discriminated
Pydantic models that reject unknown fields, unsupported versions, empty values, and duplicate IDs.
Ambiguous-question cases declare either a clarification response with no SQL or an explicit
assumption paired with read-only SQL.
Unanswerable-question cases declare the reviewed no-answer response required when the requested data
is absent from the live schema.
Schema-collision cases live in a separate wide-dataset document and declare the exact enriched
schema, table, and column that must rank first among repeated identifiers.
Stale-enrichment-metadata cases live with the wide-dataset document and declare the reviewed
metadata reference class that must fail validation before schema documents are embedded.

Run each SQL attempt through the real agent loop with zero retries and require a validation-stage
failure. Injection cases additionally require the source value to be observed in the schema supplied
to generation. Tests replace the execution node with a failing sentinel to prove reviewed unsafe SQL
never reaches it. The command exits unsuccessfully unless every case passes. Generated audit reports
remain under ignored `evals/results/` paths.

Resolve ambiguity before generation. A clarification terminates with a typed response before SQL or
execution. An assumption remains attached to the terminal query result so callers cannot present the
answer as an unexplained guess. The adversarial evaluator requires each reviewed response and status
to match its case contract.
Unanswerable cases use the same pre-generation resolver boundary and require a typed `no_answer`
terminal state with no SQL generated.

Evaluate schema collisions against the deterministic 32-table fixture and reviewed enrichment using
the same embedding and cosine tie-break logic as offline retrieval metrics. Require an exact rank-1
column match; a merely present top-k result does not pass.

Activate enrichment metadata through a strict reviewed-and-current merge boundary before retrieval
indexing. This boundary rejects unreviewed documents and unknown schema, table, or column references
instead of silently falling back to raw schema text. Stale-metadata adversarial cases use a sentinel
embedding provider so any attempted indexing or retrieval after failed validation becomes a test
failure.

## Consequences

- Safety evaluation does not depend on credentials or provider refusal behavior.
- Natural-language attacks and their worst-case SQL translations remain reviewable together.
- Additional Phase 7 categories can extend the versioned contract with category-specific outcomes.
- Live-model robustness remains a separate measurement from the mandatory SQL enforcement layer.
- Missing-schema requests fail as explicit no-answer outcomes instead of execution-stage hallucinations.
- Wide collision evaluation fails closed when reviewed enrichment metadata is absent or stale.
- Retrieval setup fails closed before indexing when enrichment references do not match the live schema.
