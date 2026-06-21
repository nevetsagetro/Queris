# ADR 0003: Use Gemini with Environment Credentials

- **Status:** Accepted
- **Date:** 2026-06-21

## Context

ADR 0002 selected OpenAI for the Phase 2 baseline. The project owner chose to use a Gemini API key
instead. The existing provider boundary allows this change without modifying schema inspection, SQL
validation, read-only execution, or evaluation scoring.

## Decision

Replace the OpenAI integration with the official Google Gen AI Python SDK (`google-genai`). Generate
SQL with `models.generate_content` and use `gemini-3.5-flash` as the configurable Phase 2 baseline
model. Keep generation behind the existing Queris interface so tests remain deterministic and
offline.

Read the API key only from `GEMINI_API_KEY` in the process environment. Allow the model to be
overridden with `GEMINI_MODEL`. Do not read credentials from source files, CLI arguments, committed
configuration, or application-managed credential stores.

Local development may source an ignored `.env` file through shell tooling; Queris does not load it.
Deployment environments must inject the variables through their secret manager. Tests must replace
the provider client and must not require a real key or network access.

## Consequences

- ADR 0002 and the OpenAI SDK integration are superseded.
- Credentials remain outside application state, prompts, logs, and version control.
- A developer must export `GEMINI_API_KEY` before making a live generation request.
- The initial Gemini model is an evaluation baseline, not a permanent provider or model commitment.
