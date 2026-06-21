from pathlib import Path

import pytest

from queris.sample_data import create_sample_database


@pytest.fixture
def sample_database(tmp_path: Path) -> Path:
    return create_sample_database(tmp_path / "retail.duckdb")
