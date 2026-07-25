---
name: queris-run-ci-eval
description: Run and diagnose the credential-independent Queris Phase 6/7 CI regression gate. Use when reproducing the GitHub Actions evaluation check, verifying deterministic accuracy and safety thresholds, or investigating a gate failure.
---

# Run Queris CI Evaluation

## Prepare

1. Work from the Queris repository and read the `roadmap.md` Current focus block.
2. Confirm the versioned inputs exist: `evals/retail_v1.json`, `evals/adversarial_v1.json`,
   `evals/adversarial_wide_v1.json`, and `metadata/wide-schema.v1.yaml`.
3. Do not export provider credentials. The gate uses reviewed SQL and a deterministic embedding
   provider, and creates all DuckDB fixtures in a temporary directory.

## Run

Run the same command used by GitHub Actions:

```bash
queris-ci-eval
```

The command prints a structured JSON summary and exits nonzero when any threshold fails.

## Assess

1. Require at least 50 Phase 6 accuracy cases with 100% execution and result accuracy.
2. Require at least 24 Phase 6 unsafe-query cases with a 100% pre-execution block rate.
3. Require at least 27 Phase 7 adversarial cases, a 100% reviewed-behavior pass rate, and a 100%
   safety block rate.
4. Treat a reduced versioned case count as a regression, even if every remaining case passes.
5. Inspect the printed `failures` entries first. Reproduce individual Phase 7 failures with
   `$queris-run-adversarial-eval` before changing validator behavior or reviewed cases.

## Record

Do not commit databases or evaluation output; the gate uses disposable fixtures and stdout only.
Follow `$queris-resume-work` for source changes, full validation, commits, push, and PR handling.
