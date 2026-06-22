---
name: queris-run-agent-loop-eval
description: Run and record the Queris Phase 5 self-correction exit evaluation. Use when validating or repeating the five deliberately failing text-to-SQL cases, checking the 3/5 majority threshold, investigating correction failures, producing local agent-loop JSONL audit results, or advancing the roadmap from Phase 5 to Phase 6.
---

# Run Queris Agent Loop Evaluation

## Prepare

1. Work from the Queris repository and read the `roadmap.md` Current focus block.
2. Confirm `evals/agent_loop_questions.json` contains exactly five reviewed cases with deliberately invalid `initial_sql` values.
3. Confirm `GEMINI_API_KEY` is present in the process environment without printing it. Never place it in repository files, CLI arguments, logs, or shell history.
4. Use `GEMINI_MODEL` only when intentionally overriding the ADR 0003 model.
5. Create `data/retail.duckdb` with `queris-sample-data` only when absent. Keep fixture creation separate from the read-only evaluation runtime.

## Run

Run from the repository virtual environment:

```bash
queris-agent-eval data/retail.duckdb \
  --questions evals/agent_loop_questions.json \
  --output evals/results/agent_loop.jsonl \
  --max-retries 3
```

Keep `evals/results/` local and ignored. Do not commit generated databases or audit output.

## Assess

1. Require exactly five JSONL records and at least three correct recovered results.
2. Count a case only when the injected initial SQL failed, `retry_count > 0`, and the final rows match the versioned expected result.
3. Inspect every incorrect record's `final_sql`, `failure_stage`, `error`, `retry_count`, and `retries_exhausted` values.
4. Do not count an executable but incorrect result as recovered successfully.
5. If credentials are unavailable, do not fabricate a score or complete Phase 5. Run `python -m pytest tests/test_agent_evaluation.py` to verify the offline harness.

## Record The Checkpoint

After a real five-case run, update `roadmap.md` with the model, correct count, threshold, and pass/fail state. Advance to Phase 6 only after the branch containing the result is reviewed and merged. Commit only versioned cases, source, tests, skill, and checkpoint documentation. Run the `$queris-resume-work` validation commands before committing.
