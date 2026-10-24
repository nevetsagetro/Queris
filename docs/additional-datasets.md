# Additional demo datasets

Queris can materialize two structurally different public datasets locally:

```bash
queris-dataset chinook
queris-dataset penguins
```

Both commands write ignored DuckDB files under `data/` and refuse to overwrite an existing file.
The local app discovers them automatically when `QUERIS_DATABASE_DIR=data` is configured.

## Chinook

Chinook models a digital music store with related artists, albums, tracks, customers, invoices,
and invoice lines. The source is the Chinook SQLite fixture from the
[Chinook database project](https://github.com/lerocha/chinook-database), distributed under MIT.

## Palmer Penguins

Palmer Penguins is a compact scientific dataset with species, island, measurements, sex, and year.
The source is published by Allison Horst and documents data collected by the Palmer Station
Antarctica LTER; the project describes the data as CC0.

These datasets are setup fixtures, not runtime tools. Query execution remains read-only.
