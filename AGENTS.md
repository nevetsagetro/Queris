# Repository Guidelines

## Project Structure & Module Organization

Queris has completed its safe DuckDB core and schema introspection. `README.md` defines scope and security boundaries; the `roadmap.md` Current focus block owns the active stage and resume point. Read that block first and update it when focus changes.

In a fresh session, invoke `$queris-resume-work` to recover context and follow the branch, validation, commit, push-before-transition, and checkpoint workflow.

Invoke `$queris-run-baseline-eval` when rerunning or recording the versioned text-to-SQL baseline, or when investigating a live evaluation failure.

Invoke `$queris-run-agent-loop-eval` when running or recording the Phase 5 self-correction exit evaluation, checking its 3/5 threshold, or investigating a correction failure.

Invoke `$queris-run-adversarial-eval` when running or recording Phase 7 destructive-intent safety
cases, checking the 100% blocked-before-execution threshold, or investigating an adversarial failure.

When introducing or materially changing a repeatable multi-step repository process, create or update a focused skill under `skills/` and reference it from this file when contributors should invoke it. Keep one-off implementation details in the task or code instead of turning them into skills.

Production code lives under `src/queris/` and tests mirror it in `tests/`. Keep database access, sample setup, schema inspection, SQL validation, and future evaluation concerns in focused modules. Store accepted decisions in `docs/adr/`. Generated databases and credentials never belong in Git.

## Build, Test, and Development Commands

Create a virtual environment and install the package with development tools using `python -m pip install -e '.[dev]'`. There is no executable service yet. Use these checks:

- `python -m pytest`: run the complete test suite.
- `python -m ruff check .`: check Python style and common defects.
- `python -m ruff format --check .`: verify formatting.
- `pre-commit run --all-files`: run repository checks before proposing a commit.
- `queris-sample-data data/retail.duckdb`: create the local deterministic fixture.
- `queris-schema data/retail.duckdb --samples 3`: print structured schema JSON.
- `queris-enrichment-draft data/retail.duckdb`: print inactive version 1 enrichment YAML for human review.
- `queris-wide-data data/wide.duckdb`: create the deterministic 32-table ambiguous-schema fixture.
- `queris-retrieval-eval data/wide.duckdb metadata/wide-schema.v1.yaml evals/wide_schema_retrieval.json --top-k 5`: compare raw and enriched retrieval offline.
- `queris-agent-eval data/retail.duckdb`: run the five-case Phase 5 self-correction exit evaluation.
- `queris-adversarial-eval data/retail.duckdb`: run versioned Phase 7 destructive-intent safety cases.
- `queris-evaluation-report data/retail.duckdb`: run the full Phase 6 evaluation and write a table plus JSON report.
- `queris-eval data/retail.duckdb`: run the versioned 10-question baseline and write ignored local JSONL results.

## Coding Style & Naming Conventions

Use four-space indentation, type annotations, and concise public-interface docstrings. Use `snake_case` for modules/functions, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants. Keep functions small and use Pydantic at structured boundaries. Update roadmap checkboxes with completed work.

## Testing Guidelines

Use `pytest`; name files `test_<module>.py` and tests `test_<behavior>`. SQL execution changes must cover allowed queries and rejected mutations. Add prompt-injection, ambiguity, retry, and audit cases where relevant. Keep fixtures deterministic. When Phase 3 work updates the SQL policy, keep the roadmap's current focus aligned with the live validation state.

Version and review schema-enrichment metadata before indexing. Test stale references and retrieval with ambiguous identifiers.

## Commit & Pull Request Guidelines

Follow `CONTRIBUTING.md`: branch from updated `main`, use typed kebab-case names, and write Conventional Commit subjects such as `feat(sql): reject stacked statements`. Keep commits focused. Pull requests explain the problem, implementation, verification, and security-impacting changes.

## Security & Configuration

Treat the security boundaries in `README.md` as acceptance criteria from the first implementation. Never commit secrets or generated database files. Architectural changes require an ADR and a corresponding roadmap update.
