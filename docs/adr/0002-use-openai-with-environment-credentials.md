# ADR 0002: Use OpenAI with Environment Credentials

- **Status:** Accepted
- **Date:** 2026-06-21

## Context

Phase 2 needs one LLM provider for a minimal text-to-SQL baseline. The integration must be easy to
replace, test without network access, and configure without storing credentials in the repository.
Provider comparison, orchestration, and model benchmarking are later roadmap concerns.

## Decision

Use the OpenAI Responses API through the official Python SDK. Keep the SDK behind a small Queris
generation interface so prompt construction and pipeline tests can use deterministic fakes.

Read the API key only from `OPENAI_API_KEY` in the process environment. Do not read keys from source
files, CLI arguments, committed configuration, or application-managed credential stores. Allow the
model to be selected with `OPENAI_MODEL`; use `gpt-5.4-mini` as the Phase 2 baseline default until an
evaluation justifies changing it.

Local development may use an ignored `.env` file only through developer shell tooling; Queris will
not load it. Deployment environments must inject the same variables through their secret manager.
Tests must replace the provider client and must not require a real key or network access.

## Consequences

- Phase 2 has one concrete, low-ceremony provider path while retaining a replaceable boundary.
- Credentials stay outside application state, logs, prompts, and version control.
- A developer must export `OPENAI_API_KEY` before making a live generation request.
- The initial model choice is a baseline, not a claim that it is optimal for accuracy, cost, or
  latency; later evaluations may change it or add providers.
