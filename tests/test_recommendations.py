from pathlib import Path

from queris.database import read_only_connection
from queris.recommendations import recommend_runs
from queris.schema import introspect_schema


def test_recommendations_are_bounded_and_schema_aware(sample_database: Path) -> None:
    with read_only_connection(sample_database) as connection:
        schema = introspect_schema(connection, sample_limit=0)

    recommendations = recommend_runs(schema)

    assert 0 < len(recommendations) <= 12
    assert all(recommendation.tables for recommendation in recommendations)
