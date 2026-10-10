import numpy as np
import pandas as pd

from src.modeling.budget import evaluate_budget
from src.modeling.config import BUDGETS, PRIMARY_BUDGET, budget_key, budget_label
from src.modeling.uncertainty import bootstrap_uncertainty, bootstrap_year, weighted_capture

LABEL = budget_label(PRIMARY_BUDGET)
KEY = f"capture_at_{budget_key(PRIMARY_BUDGET)}"


def test_unit_weights_reproduce_the_observed_capture():
    rng = np.random.default_rng(1)
    n = 80
    group = pd.DataFrame(
        {
            "segment_id": [f"S{i:02d}" for i in range(n)],
            "risk_percentile": rng.random(n),
            "length_m": rng.uniform(10, 300, n),
            "actual_break": rng.integers(0, 2, n),
        }
    )
    ordered = group.sort_values(["risk_percentile", "segment_id"], ascending=[False, True])
    got = weighted_capture(
        np.ones((1, n)), ordered["length_m"].to_numpy(), ordered["actual_break"].to_numpy(float), BUDGETS
    )[0]
    np.testing.assert_allclose(got, [evaluate_budget(group, b).capture for b in BUDGETS])


def test_identical_rankings_get_identical_replicates(evaluation):
    """Every method sees the same resample, so the bootstrap is paired."""
    year = evaluation.predictions[evaluation.predictions["test_year"] == 2023]
    oldest = year[year["method"] == "oldest"]
    replicates = bootstrap_year(
        pd.concat([oldest, oldest.assign(method="oldest_twin")]), BUDGETS, 200, seed=3, year=2023
    )
    np.testing.assert_array_equal(replicates["oldest"], replicates["oldest_twin"])


def test_intervals_are_ordered_bounded_and_cover_the_estimate(evaluation):
    for method, block in evaluation.metrics["uncertainty"]["capture"][LABEL].items():
        low, high = block["ci_mean"]
        assert 0 <= low <= high <= 1
        assert low <= evaluation.metrics["methods"][method][KEY] <= high


def test_champion_difference_vs_oldest_is_reported(evaluation):
    diff = evaluation.metrics["uncertainty"]["difference_vs_oldest"][LABEL]["champion"]
    low, high = diff["ci_mean"]
    assert low <= high
    assert 0 <= diff["share_of_resamples_above_zero"] <= 1
    assert set(diff["by_year"]) == {"2021", "2022", "2023"}


def test_bootstrap_is_reproducible_and_seed_dependent(evaluation):
    predictions, champion = evaluation.predictions, evaluation.metrics["champion_method"]
    first = bootstrap_uncertainty(predictions, champion, n_resamples=100, seed=1)
    again = bootstrap_uncertainty(predictions, champion, n_resamples=100, seed=1)
    other = bootstrap_uncertainty(predictions, champion, n_resamples=100, seed=2)
    assert first == again
    assert first["capture"] != other["capture"]
