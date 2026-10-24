---
name: queris-register-dataset
description: Register and validate a new local DuckDB dataset through Queris's read-only workflow.
---

# Register a Dataset

Use this workflow when adding a new `.duckdb` file that should be selectable by the API and frontend.

1. Put the existing DuckDB file in the configured data directory. Do not modify it.
2. Run the workflow with the public provenance and explicit review outputs:

   ```bash
   queris-dataset-workflow data/example.duckdb \
     --metadata-dir metadata \
     --dataset-name "Example Dataset" \
     --source-name "Public publisher" \
     --source-url "https://example.org/dataset" \
     --license "Publisher terms" \
     --draft metadata/example.v1.yaml \
     --report reports/example.workflow.json
   ```

3. Review the generated enrichment YAML, set `reviewed: true`, and rerun the workflow.
4. Start or reload the API. The dataset is selectable only when a public source URL is registered.

The command profiles tables and probable relationships, generates at least 50 deterministic
read-only starters when the schema supports them, executes every starter, and writes only the
requested metadata/report files. The source database is always opened in read-only mode.
