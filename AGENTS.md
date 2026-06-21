# Repository Guidelines

## Project Structure & Module Organization

Queris is in Phase 0 with package and quality-tool scaffolding only. `README.md` defines product scope and security boundaries; the `roadmap.md` Current focus block owns the active stage and resume point. Read that block first, update it when focus changes, and do not duplicate specifications across documents.

When introducing the Python MVP, keep production code under `src/queris/` and mirror it in `tests/`. Separate API, schema retrieval, SQL validation, execution, and evaluation concerns into focused modules. Put sample data in `data/` only when its license and provenance are documented; keep generated databases and credentials out of Git. Record significant architectural choices in `docs/adr/`.

## Build, Test, and Development Commands

Create a virtual environment and install the package with development tools using `python -m pip install -e '.[dev]'`. There is no executable service yet. Use these checks:

- `python -m pytest`: run the complete test suite.
- `python -m ruff check .`: check Python style and common defects.
- `python -m ruff format --check .`: verify formatting.
- `pre-commit run --all-files`: run repository checks before proposing a commit.

## Coding Style & Naming Conventions

For Python, use four-space indentation, type annotations, and concise docstrings for public interfaces. Name modules, functions, and variables with `snake_case`; classes with `PascalCase`; constants with `UPPER_SNAKE_CASE`. Keep functions small and use Pydantic models at API boundaries. Follow accepted ADRs and update roadmap checkboxes in the same change that completes them.

## Testing Guidelines

Use `pytest` when the test infrastructure is introduced. Name files `test_<module>.py` and tests `test_<behavior>`. Every SQL execution change must cover allowed read-only queries and rejected `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, and `CREATE` statements. Include prompt-injection, ambiguous-input, retry-limit, and audit-log cases where relevant. Evaluation fixtures should remain deterministic and versioned.

Version and review schema-enrichment metadata before indexing. Test stale references and retrieval with ambiguous identifiers.

## Commit & Pull Request Guidelines

Follow `CONTRIBUTING.md`: branch from updated `main`, use a typed kebab-case branch name, and write Conventional Commit subjects such as `feat(sql): reject stacked statements`. Keep each commit focused and include its tests or documentation. Pull requests must explain the problem, implementation, and verification; call out schema, dependency, configuration, and security-boundary changes explicitly.

## Security & Configuration

Treat the security boundaries in `README.md` as acceptance criteria from the first implementation. Never commit secrets or generated database files. Architectural changes require an ADR and a corresponding roadmap update.
