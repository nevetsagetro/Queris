# Contributing to Queris

## Branches

Create every change from an updated `main`; do not commit directly to `main`. Use lowercase kebab-case names with one of these prefixes:

- `feat/schema-introspection` for user-visible capabilities.
- `fix/sql-validator-bypass` for defect corrections.
- `docs/evaluation-guide` for documentation-only work.
- `chore/dependency-update` for tooling and maintenance.

Keep a branch focused on one deliverable. Rebase it on `origin/main` before opening a pull request; do not merge `main` into the branch solely to synchronize it.

## Commits

Use Conventional Commit subjects in imperative form:

```text
<type>(optional-scope): <specific change>
```

Allowed types are `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, and `ci`. Examples:

- `feat(sql): reject multi-statement queries`
- `test(schema): cover stale enrichment metadata`
- `docs: record the active roadmap checkpoint`

Each commit must represent one reviewable concern, include its tests or documentation, and pass `pre-commit run --all-files` plus `python -m pytest`. Do not commit secrets, local databases, generated reports, caches, or virtual environments. Avoid vague subjects such as `updates`, `changes`, or `work in progress`.

## Pull Requests

Open a pull request into `main` with a concise problem statement, implementation summary, and verification commands. Link the relevant issue or roadmap item. Call out changes to security boundaries, dependencies, configuration, datasets, or architecture. Include screenshots only for UI changes. Prefer rebase-and-merge or squash-and-merge according to repository settings, and delete the branch after merge.
