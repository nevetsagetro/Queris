import json
from pathlib import Path

import duckdb

from queris.query_intelligence import generate_query_intelligence


def test_query_intelligence_persists_validated_starters(tmp_path: Path) -> None:
    database = tmp_path / "events.duckdb"
    connection = duckdb.connect(str(database))
    connection.execute("CREATE TABLE events (event_id INTEGER, category VARCHAR, value DOUBLE)")
    connection.execute("INSERT INTO events VALUES (1, 'a', 2.5), (2, 'b', 4.0)")
    connection.close()

    output = tmp_path / "intelligence" / "events.queries.json"
    report = generate_query_intelligence(database, output=output)

    assert report.generated_query_count >= 50
    assert report.validated_query_count == report.generated_query_count
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert len(payload) == report.validated_query_count
    assert all(item["validated"] is True for item in payload)
    assert all(item["chart_recommendation"] is not None for item in payload)
