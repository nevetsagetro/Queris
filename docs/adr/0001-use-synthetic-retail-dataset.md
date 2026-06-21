# ADR 0001: Use a Synthetic Retail Dataset

- **Status:** Accepted
- **Date:** 2026-06-21

## Context

Phase 1 needs stable analytics data for schema introspection and safety tests. A downloaded public dataset would add network availability, licensing, provenance, and upstream-change risks before those concerns provide value. The product examples require categories, regions, dates, revenue, and cost data.

## Decision

Use a small synthetic retail dataset generated deterministically by trusted setup code. Its schema contains regions, categories, products, orders, and order items. Generated DuckDB files remain local and are excluded from Git.

The generator is development and test infrastructure, not an agent tool. Runtime query execution opens the resulting database separately in read-only mode. The fixture can be replaced or supplemented later when evaluation requirements justify a larger public dataset.

## Consequences

- Tests are reproducible, fast, offline, and free of third-party data licensing concerns.
- The schema directly supports margin analysis across category, region, and time.
- The fixture is not representative of production scale or messy real-world data, so later evaluation phases must add wider and adversarial schemas.
