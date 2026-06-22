---
name: queris-start-next-phase
description: Verify Queris phase-transition prerequisites and begin the next roadmap phase from reviewed main. Use only when explicitly invoked with $queris-start-next-phase after a phase-completing checkpoint has been implemented, pushed, and submitted for review.
---

# Start The Next Queris Phase

Treat explicit invocation as authorization to perform the standard non-force fetch and push actions
required by `CONTRIBUTING.md`. Never force-push, merge locally into a protected base, bypass review,
or expose credentials.

## Recover The Transition

1. Locate the repository with `git rev-parse --show-toplevel`.
2. Read `AGENTS.md`, `CONTRIBUTING.md`, and only the `roadmap.md` Current focus block.
3. Inspect `git status --short --branch`, `git log -5 --oneline --decorate`, branch upstreams, and
   `@{upstream}..HEAD` where available.
4. Stop rather than discard unrelated work when the worktree is not clean enough to transition.
5. Fetch `origin` with pruning and identify the commit that completes the current phase.

## Enforce The Merge Gate

Before writing next-phase code, require all of the following:

- The phase-completing branch is clean, pushed, and synchronized with its upstream.
- A pull request exists against the correct base.
- The pull request is not a draft, has no conflicts, passes required checks, and has required review.
- The pull request was merged through GitHub.
- `origin/main` contains the phase-completing checkpoint commit.

Use available GitHub tooling to inspect or create the pull request. When PR tooling is unavailable,
share the exact compare URL and stop at the review gate. Do not infer approval from a pushed branch.

## Prepare The Next Phase

After the merge gate passes:

1. Switch to `main` and fast-forward it to `origin/main`; never merge a feature branch locally.
2. Read the upcoming phase block in `roadmap.md`, its exit criteria, and files directly named by the
   resume point.
3. Create one focused branch from updated `main` using the allowed `<type>/<kebab-case>` convention.
4. State the recovered stage, acceptance boundary, immediate task, and branch before editing.
5. Implement the smallest roadmap item with a verifiable terminal condition and proportional tests.

## Deliver The Work

Read `../queris-resume-work/SKILL.md` and follow its Deliver The Task and Validate And Commit
sections. In addition:

- Keep trusted fixture/setup writes separate from read-only agent execution.
- Convert any new or materially changed repeatable multi-step process into a focused skill under
  `skills/`, and register its invocation in `AGENTS.md`.
- Update the roadmap checklist and Current focus in the same change.
- Run pre-commit, the full test suite, and Git diff checks before committing.
- Push a completed checkpoint without pausing for separate confirmation; explicit invocation is the
  request to follow the repository workflow.
- Share the pull-request URL for user review and approval. Do not start another phase until it is
  merged.

Finish with the branch, commits, validation, PR or blocking review state, and exact resume point.
