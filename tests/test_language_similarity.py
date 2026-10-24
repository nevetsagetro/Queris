import json
from pathlib import Path

from queris.language_similarity import find_similar_validated_questions


def test_similarity_can_reuse_local_validated_intelligence(tmp_path: Path) -> None:
    intelligence = tmp_path / "queries.json"
    intelligence.write_text(
        json.dumps(
            [
                {
                    "id": "monthly-revenue",
                    "question": "What was revenue by month?",
                    "sql": "SELECT month, SUM(revenue) FROM orders GROUP BY month",
                }
            ]
        ),
        encoding="utf-8",
    )

    matches = find_similar_validated_questions("Show revenue by month", intelligence)

    assert matches[0].demo_id == "monthly-revenue"
    assert matches[0].sql_hint is not None
