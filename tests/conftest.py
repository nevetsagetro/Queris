from pathlib import Path

import pytest

from queris.safety_evaluation import UNSAFE_QUERY_CASES
from queris.sample_data import create_sample_database

MALICIOUS_SQL_CASES = [pytest.param(case.sql, id=case.id) for case in UNSAFE_QUERY_CASES]


@pytest.fixture
def sample_database(tmp_path: Path) -> Path:
    return create_sample_database(tmp_path / "retail.duckdb")


@pytest.fixture(params=MALICIOUS_SQL_CASES)
def malicious_sql(request: pytest.FixtureRequest) -> str:
    """Return one hand-written SQL policy bypass attempt."""
    return request.param
