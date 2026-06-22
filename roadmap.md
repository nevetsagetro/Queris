# Queris Roadmap

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

This is the source of truth for pending decisions, delivery order, and progress. Product scope and non-negotiable security boundaries live in [`README.md`](README.md).

## Current focus

- **Active stage:** Phase 5 — Agent Loop (`[~]`)
- **Latest checkpoint:** added a five-case injected-failure evaluation harness and repeatable skill for the Phase 5 self-correction exit criterion.
- **Completed work:** completed all Phase 5 implementation items and offline-validated expected-result scoring for deliberately failing initial SQL.
- **Pending next:** run the five cases with Gemini and require at least 3/5 correct recovered results before transitioning to Phase 6.
- **Resume point:** invoke `$queris-run-agent-loop-eval`, inspect `evals/results/agent_loop.jsonl`, and record the model plus pass/fail result; the 2026-06-21 live attempt was not started because external-tool execution was unavailable.
- **Last updated:** 2026-06-21

---

## Phase 0 — Decisions & Scaffolding
**Goal:** resolve the blocking technical choices so Phase 1 can start unambiguously.

- [x] Pick agent orchestrator: standalone LangGraph (ADR 0007)
- [x] Pick vector store: DuckDB VSS for the rebuildable local MVP (ADR 0006)
- [x] Pick LLM provider(s) and credential management approach (ADR 0003; supersedes ADR 0002)
- [x] Choose a deterministic synthetic retail dataset (ADR 0001)
- [x] Confirm the initial layout (`src/queris/`, `tests/`, `evals/`, `data/`, and an optional `frontend/`)
- [x] Set up `pyproject.toml`, linting, tests, and pre-commit
- [x] Document branch, commit, and pull-request conventions

**Exit criteria:** repo skeleton exists, dependencies installable, dataset loads into DuckDB.

---

## Phase 1 — Safe DuckDB Core + Schema Introspection
**Goal:** establish safe database access and structured schema inspection before adding an LLM.

- [x] Load sample dataset into a local DuckDB file
- [x] Implement SQLGlot parsing and an explicit read-only statement whitelist
- [x] Reject multi-statement queries before execution
- [x] Open execution connections with `read_only=True` as defense in depth
- [x] Write a schema-introspection function (tables, columns, types, sample values)
- [x] Unit tests for the initial allowed/forbidden SQL policy
- [x] Unit tests for schema introspection against the selected dataset

**Exit criteria:** one command prints a structured JSON schema; all mutation and stacked-statement fixtures are blocked before DuckDB execution.

---

## Phase 2 — Baseline Text-to-SQL (no RAG)
**Goal:** prove a minimal, safe loop works end-to-end before adding retrieval.

- [x] Prompt template: full schema + user question → SQL string
- [x] Pass every generated statement through the Phase 1 validator before execution
- [x] Manually test against ~10 hand-picked questions
- [x] Log every (question, generated SQL, result) triple to a local file

**Exit criteria:** at least 7/10 hand-picked questions return correct results, end-to-end, with full schema in the prompt.

---

## Phase 3 — Safety Hardening
**Goal:** expand the Phase 1 safety foundation and verify defense in depth.

- [x] Cover all forbidden SQLGlot node types, including `ATTACH`, `COPY`, pragmas, and extension operations
- [x] Verify legitimate `SELECT` and `WITH` queries pass unchanged
- [x] Add bypass attempts involving comments, casing, nesting, and unusual syntax
- [x] Confirm rejected SQL never reaches the database adapter

**Exit criteria:** 100% of a hand-written "malicious query" test set is blocked before reaching DuckDB.

---

## Phase 4 — Schema Enrichment + RAG
**Goal:** make ambiguous schemas understandable, then retrieve only the relevant tables and columns instead of sending the full schema.

- [x] Define a versioned YAML format for table and column descriptions, business terms, units, and aliases
- [x] Merge optional enrichment metadata with introspected names, types, and safe sample summaries
- [x] Provide a command that drafts descriptions from schema metadata; require human review before activation
- [x] Validate enrichment against the live schema and report stale or unknown table/column references
- [x] Generate embeddings for enriched descriptions, raw identifiers, and safe sample summaries
- [x] Store embeddings in DuckDB VSS (ADR 0006)
- [x] Implement cosine-similarity retrieval: question → top-k relevant tables/columns
- [x] Replace "full schema in prompt" with "retrieved schema in prompt" in the pipeline from Phase 2
- [x] Add a synthetic wide schema (30+ tables) with ambiguous identifiers such as `amt`, `qty`, and `flg_x`
- [x] Compare retrieval quality with and without enrichment to quantify its contribution

**Exit criteria:** retrieval precision/recall is measured against hand-labeled question-to-column pairs, and enrichment produces a documented improvement on the ambiguous-schema fixture.

---

## Phase 5 — Agent Loop: Generate → Validate → Execute → Self-Correct
**Goal:** turn the linear pipeline into a think-act-observe loop that recovers from its own SQL errors.

- [x] Wrap generation, the Phase 1/3 validation layer, and execution into a single orchestrated loop
- [x] On DuckDB syntax/execution error, feed the error message back to the LLM and retry
- [x] Cap retries (configurable, default 3) and fail gracefully with an explanation after the cap
- [x] Track retry count per query (needed for Phase 6 metrics)
- [x] Integrate standalone LangGraph as selected in ADR 0007

**Exit criteria:** a deliberately malformed-prone question (e.g. ambiguous join) self-corrects within the retry cap on a majority of runs.

---

## Phase 6 — Evaluation Harness
**Goal:** the project's actual differentiator. Without this, it's "just another demo."

- [ ] Author 50–100 questions with expected SQL and expected result, covering: simple aggregation, multi-table joins, time filtering, group-by + having, nested subqueries
- [ ] Decide and document the storage format (YAML/JSON/CSV) for the eval set
- [ ] Implement metrics:
  - [ ] Execution accuracy (did it run without error?)
  - [ ] Result accuracy (does the output match expected, allowing for row/column order differences?)
  - [ ] Blocked-unsafe-query rate (from the safety test suite)
  - [ ] Average number of retries (from Phase 5)
  - [ ] Latency per query (p50/p95)
  - [ ] Token/cost per query
- [ ] Build a CLI/script to run the full eval set and output a report (table + JSON)
- [ ] Store historical eval runs so regressions are visible over time

**Exit criteria:** running one command produces a full metrics report against the 50–100 question set.

---

## Phase 7 — Adversarial Test Suite
**Goal:** stress-test the safety and robustness boundaries explicitly, not just the happy path.

- [ ] Destructive intent: "delete the orders table", "drop all data", etc. → must be blocked, not just refused conversationally
- [ ] Prompt injection embedded in data fields (e.g. a product description containing "ignore previous instructions and...") → must not alter agent behavior
- [ ] Ambiguous questions (no clear single interpretation) → agent should ask for clarification or state the assumption made, not silently guess
- [ ] Similar/colliding column names across tables → correct table must be picked, or the ambiguity surfaced
- [ ] Unanswerable questions (data doesn't exist in the schema) → agent must say so, not hallucinate a query
- [ ] Incorrect or stale enrichment metadata → validation must fail before indexing
- [ ] Add all of the above as a permanent subset of the Phase 6 eval harness, with their own pass/fail criteria

**Exit criteria:** 100% block rate on destructive/injection cases; documented behavior (not necessarily 100% "correct" by human judgment) on ambiguous/unanswerable cases.

---

## Phase 8 — Demo UX
**Goal:** make the system demoable live, with visualization and explanation, per the README flow.

- [ ] Streamlit app: question input → SQL shown → results table → chart → plain-language explanation
- [ ] Persist query + sources used (tables/columns) per session, per the README's "save the query and sources" requirement
- [ ] Surface retry count / latency / blocked status in the UI for transparency during demos

**Exit criteria:** a non-technical person can ask 5 example questions live and get correct, explained results.

---

## Phase 9 — Productionization
**Goal:** package it as something that looks deployable, not just a notebook.

- [ ] Wrap the agent pipeline in a FastAPI service with Pydantic request/response models
- [ ] Dockerize (API + DuckDB file or volume)
- [ ] GitHub Actions: run lint + unit tests on every PR
- [ ] GitHub Actions: run the Phase 6/7 eval suite on every PR to main, failing the build on regressions below a threshold
- [ ] Basic structured logging (request id, latency, retries, blocked/allowed)

**Exit criteria:** `docker compose up` serves the API; a PR with a deliberately broken validator fails CI via the eval suite.

---

## Phase 10 — Stretch Goals (optional, post-portfolio-ready)
- [ ] React/TypeScript frontend replacing/complementing Streamlit
- [ ] Multi-dataset support (schema switch at runtime)
- [ ] Side-by-side comparison of multiple LLMs on the same eval set (accuracy vs cost vs latency)
- [ ] Cost/latency dashboard over historical eval runs
- [ ] Natural-language follow-up questions (conversational context across queries)

---

## Suggested sequencing summary

```
Phase 0 → 1 (safe core) → 2 (baseline) → 3 (hardening) → 4 (enrichment + RAG) → 5 (agent loop)
                                              ↓
                              6 (eval harness) ↔ 7 (adversarial tests)
                                              ↓
                                    8 (demo UX) → 9 (production)
                                              ↓
                                      10 (stretch, optional)
```

Phases 6 and 7 should be treated as a pair and kept growing throughout — every new capability (Phase 4, 5, 8...) should add corresponding cases to the eval set rather than being considered "done" in isolation.
