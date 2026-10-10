import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.modeling.evaluate import run_evaluation  # noqa: E402
from src.modeling.synthetic import make_synthetic_pipe_year  # noqa: E402

TEST_YEARS = [2021, 2022, 2023]


@pytest.fixture(scope="session")
def pipe_year():
    """Synthetic Contract A. Session-scoped: tests must copy before mutating."""
    return make_synthetic_pipe_year(n_segments=300, seed=11)


@pytest.fixture(scope="session")
def evaluation(pipe_year):
    return run_evaluation(pipe_year, test_years=TEST_YEARS)
