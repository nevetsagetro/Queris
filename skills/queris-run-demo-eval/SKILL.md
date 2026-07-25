---
name: queris-run-demo-eval
description: Run and assess the Queris Phase 8 five-question live demo exit evaluation. Use when verifying the non-technical demo criterion, repeating the versioned demo set, investigating an incorrect or unexplained result, writing the local demo audit report, or preparing the Phase 8 completion checkpoint.
---

# Run Queris Demo Exit Evaluation

## Prepare

1. Work from the Queris repository and read the `roadmap.md` Current focus block.
2. Confirm `evals/demo_v1.json` contains exactly five reviewed cases spanning all five evaluation
   categories.
3. Confirm `GEMINI_API_KEY` is present without printing it. Never place credentials in repository
   files, arguments, logs, or chat.
4. Use `GEMINI_MODEL` only when intentionally overriding the ADR 0003 model.
5. Create `data/retail.duckdb` with `queris-sample-data` only when absent. Keep trusted fixture
   creation separate from the read-only live evaluation.

## Run

Run from the repository virtual environment:

```bash
queris-demo-eval data/retail.duckdb \
  --questions evals/demo_v1.json \
  --output evals/results/demo-exit.json \
  --max-retries 3
```

Keep `evals/results/` local and ignored. Do not commit the database or generated audit report.

## Assess

1. Require exactly five outcomes and five passes.
2. Count a case only when the safe agent succeeds, its rows match the reviewed expected result, and
   the demo presenter produces a non-empty plain-language explanation.
3. Inspect every failure's SQL, status, retry count, latency, blocked state, failure stage, and
   error.
4. Treat executable but incorrect SQL and missing explanations as failures.
5. If credentials are unavailable, do not fabricate a live result or complete Phase 8. Run
   `python -m pytest tests/test_demo_evaluation.py` to verify only the offline harness.

## Record The Checkpoint

After a real 5/5 run, update `roadmap.md` with the model, score, and pass state. Mark Phase 8 complete
only after its checkpoint branch passes the repository validation workflow and is reviewed and
merged. Commit only versioned cases, source, tests, skill, and checkpoint documentation.
