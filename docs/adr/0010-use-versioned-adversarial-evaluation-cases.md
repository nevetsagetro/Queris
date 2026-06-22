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

Run each SQL attempt through the real agent loop with zero retries and require a validation-stage
failure. Injection cases additionally require the source value to be observed in the schema supplied
to generation. Tests replace the execution node with a failing sentinel to prove reviewed unsafe SQL
never reaches it. The command exits unsuccessfully unless every case passes. Generated audit reports
remain under ignored `evals/results/` paths.

## Consequences

- Safety evaluation does not depend on credentials or provider refusal behavior.
- Natural-language attacks and their worst-case SQL translations remain reviewable together.
- Additional Phase 7 categories can extend the versioned contract with category-specific outcomes.
- Live-model robustness remains a separate measurement from the mandatory SQL enforcement layer.
