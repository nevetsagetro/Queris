# ADR 0009: Store Local Versioned Evaluation History

- **Status:** Accepted
- **Date:** 2026-06-22

## Context

Phase 6 produces a versioned JSON report, but replacing one output file makes metric changes across
runs invisible. Historical results may contain generated SQL, query results, provider usage, model
errors, and local timing data, so they are audit artifacts rather than reviewed source inputs.
Comparisons across different datasets or case sets would also produce misleading regressions.

## Decision

Append every Phase 6 run as a timestamped full JSON report under the ignored local directory
`evals/results/phase6-history/`. Continue replacing `evals/results/phase6.json` as the convenient
latest report. Do not commit generated reports.

Compare a new run with the newest earlier report only when the report format, dataset, fixture,
ordered evaluation case IDs, and ordered unsafe-query case IDs match. Report signed deltas and an
explicit preferred direction. Higher is better for execution accuracy, result accuracy, and the
blocked-unsafe-query rate. Lower is better for retry count, latency, token usage, and cost. Compare
cost only when both reports contain explicit-rate estimates. A strict movement in the wrong
direction is labeled a regression; Phase 8 CI may later add acceptance thresholds.

## Consequences

- Full historical reports retain per-case evidence for later investigation and dashboards.
- Local histories can contain sensitive operational details and remain ignored by Git.
- Case-set changes start a new comparison series instead of distorting accuracy deltas.
- Histories are local until a future storage policy deliberately introduces shared persistence.
