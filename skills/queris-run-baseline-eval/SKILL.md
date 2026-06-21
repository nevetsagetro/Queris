---
name: queris-run-baseline-eval
description: Run and record the Queris versioned text-to-SQL baseline against the retail questions. Use when executing or repeating the 10-question baseline, checking the 7/10 exit threshold, producing local JSONL audit results, investigating an evaluation failure, or updating the roadmap after a verified baseline run.
---

# Run Queris Baseline Evaluation

## Prepare

1. Work from the Queris repository and read the `roadmap.md` Current focus block.
2. Confirm `evals/baseline_questions.json` contains the reviewed versioned cases.
3. Confirm `GEMINI_API_KEY` is present in the process environment without printing its value. Never place it in repository files, CLI arguments, logs, or shell history.
4. Use `GEMINI_MODEL` only when intentionally overriding the ADR 0003 baseline model.
5. Create `data/retail.duckdb` with `queris-sample-data` only when it does not exist. Treat fixture creation as trusted setup, separate from the read-only evaluation runtime.

## Run

From the repository virtual environment, run:

```bash
queris-eval data/retail.duckdb \
  --questions evals/baseline_questions.json \
  --output evals/results/baseline.jsonl
```

Keep `evals/results/` local and ignored. Do not commit generated databases or evaluation output.

## Assess

1. Require exactly 10 JSONL records and a summary with at least 7 correct results.
2. Inspect every incorrect record's `generated_sql`, `rows`, and `error`. Do not reinterpret a failed or rejected query as correct.
3. Treat validation rejection and provider or execution errors as incorrect results.
4. If credentials are unavailable, do not fabricate a score or mark the manual baseline complete. Run `python -m pytest tests/test_evaluation.py` to verify the offline reference cases and harness instead.

## Record The Checkpoint

After a real 10-case run, update `roadmap.md` with the model, correct count, pass/fail status, and exact resume point. Commit only versioned source, tests, the skill, and checkpoint documentation. Run the repository validation commands from `$queris-resume-work` before committing.
