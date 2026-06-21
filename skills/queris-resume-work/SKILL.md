---
name: queris-resume-work
description: Resume and deliver Queris repository work from its recorded roadmap checkpoint. Use when continuing Queris in a new session, starting the next roadmap task, recovering context, updating stage status, creating a focused branch, validating changes, or preparing atomic local commits.
---

# Resume Queris Work

## Recover Context

1. Locate the repository with `git rev-parse --show-toplevel`; fall back to `~/projects/Queris` only when the current directory is not a Git worktree.
2. Read repository-level `AGENTS.md` and obey it.
3. Read only the roadmap checkpoint first:

   ```bash
   sed -n '/^## Current focus/,/^---$/p' roadmap.md
   ```

4. Inspect `git status --short --branch` and `git log -5 --oneline --decorate`.
5. Read the files directly named by the resume point and the modules/tests relevant to that task. Do not reread the entire roadmap unless sequencing or acceptance criteria are unclear.

## Prepare The Branch

- Never develop directly on `main`.
- Resume the current clean feature branch when it matches the checkpoint.
- Otherwise branch from the appropriate reviewed base using `<type>/<short-kebab-case>`.
- When the base branch is not merged, treat the new branch as stacked and report that dependency.
- Never discard unrelated changes. Stop only when they make the requested work unsafe.

## Deliver The Task

1. State the immediate plan and update it as work completes.
2. Implement the smallest roadmap item that reaches a verifiable terminal condition.
3. Keep trusted setup writes separate from the read-only agent runtime.
4. Add tests proportional to security and behavioral risk.
5. When the task introduces or changes a repeatable multi-step repository process, create or update a focused skill under `skills/`. Do not create skills for one-off implementation details.
6. Update the roadmap checklist and `Current focus` in the same change. Update `README.md` or `AGENTS.md` only when status, commands, or repository guidance changed.

## Validate And Commit

Run the repository checks:

```bash
pre-commit run --all-files
python -m pytest
git diff --check
```

Stage explicit files, inspect `git diff --cached --check` and `git diff --cached --stat`, then create focused Conventional Commits. Separate decisions/docs, infrastructure, behavior, and checkpoint updates when each is independently reviewable. Do not push unless requested; if requested, verify the upstream and report authentication failures precisely.

Finish by reporting the branch, commits, verification results, and exact roadmap resume point.
