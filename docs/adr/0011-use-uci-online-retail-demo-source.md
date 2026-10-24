# ADR 0011: Use UCI Online Retail as an optional local demo source

## Status

Accepted

## Context

The deterministic retail fixture is intentionally small and is appropriate for tests, but it
cannot demonstrate realistic price, customer, country, and time-series questions. The Streamlit
demo needs a larger local dataset without making CI dependent on a network download.

## Decision

Add `queris-online-retail` as a trusted setup command. It downloads the UCI Online Retail
workbook only when the local raw file is absent, uses DuckDB's Excel extension to import it, and
creates an ignored local database with normalized `orders`, `order_items`, `products`, and
`customers` tables. The source is attributed in the user documentation and reviewed metadata.

The downloaded workbook, extension files, and generated DuckDB database remain local artifacts.
The existing deterministic fixture remains the CI and evaluation source. The importer refuses to
replace an existing database and treats cancellation flags and negative quantities as source data;
it does not invent categories, costs, or margins that the source does not contain.

## Consequences

- The live demo can answer realistic price, customer, country, and monthly-revenue questions.
- First-time setup needs network access and DuckDB's Excel extension.
- CI remains credential- and network-independent.
- Any future evaluation set for this source must freeze a local snapshot and reviewed expected
  results rather than depend on the live download.
