import numpy as np
import pandas as pd
import pytest

from src.modeling.config import TARGET
from src.modeling.evaluate import predict_walk_forward, prepare_panel
from src.modeling.methods import (
    LogisticHazardRanker,
    OldestFirstRanker,
    RandomRanker,
    SmoothedLookupRanker,
)


def test_walk_forward_predictions_are_deterministic(pipe_year):
    first = predict_walk_forward(prepare_panel(pipe_year), [2023])
    second = predict_walk_forward(prepare_panel(pipe_year), [2023])
    pd.testing.assert_frame_equal(first, second)


def test_random_draw_ignores_row_order(pipe_year):
    test = pipe_year[pipe_year["score_year"] == 2023]
    ranker = RandomRanker(seed=1)
    forward = pd.Series(ranker.score(test), index=test.index)
    shuffled = test.sample(frac=1, random_state=0)
    backward = pd.Series(ranker.score(shuffled), index=shuffled.index)
    pd.testing.assert_series_equal(forward, backward.loc[forward.index])


def test_random_draw_changes_with_seed(pipe_year):
    test = pipe_year[pipe_year["score_year"] == 2023]
    assert not np.array_equal(RandomRanker(seed=1).score(test), RandomRanker(seed=2).score(test))


def test_oldest_first_puts_unknown_age_last():
    scores = OldestFirstRanker().score(pd.DataFrame({"age_years": [10.0, np.nan, 80.0]}))
    assert list(np.argsort(-scores)) == [2, 0, 1]


def _lookup_train(groups):
    """groups: (material, install_year, prior_breaks, pipe_years, events)."""
    records = [
        {"material": material, "install_year": install, "prior_break_count": prior, TARGET: int(i < events)}
        for material, install, prior, n, events in groups
        for i in range(n)
    ]
    return pd.DataFrame(records)


def test_lookup_falls_back_to_parent_rate_for_unseen_cells():
    lookup = SmoothedLookupRanker(prior_strength=100).fit(
        _lookup_train([("CI", 1950, 0, 400, 20), ("PVC", 1990, 0, 400, 4)])
    )
    test = pd.DataFrame({"material": ["NEWMAT"], "install_year": [1950], "prior_break_count": [0]})
    bucket_rate = lookup.tables_[0].set_index("pb_bucket").loc["0", "rate"]
    assert lookup.score(test)[0] == pytest.approx(bucket_rate)


def test_lookup_shrinks_sparse_cells_toward_parent():
    lookup = SmoothedLookupRanker(prior_strength=100).fit(
        _lookup_train([("CI", 1950, 0, 2000, 40), ("CI", 1960, 0, 5, 5)])
    )
    test = pd.DataFrame({"material": ["CI"], "install_year": [1960], "prior_break_count": [0]})
    # The 1960s cell's raw rate is 100%, but it has only five pipe-years.
    assert lookup.score(test)[0] < 0.1


def test_logistic_handles_unseen_material_and_missing_values(pipe_year):
    train = pipe_year[pipe_year["score_year"] < 2023]
    test = pipe_year[pipe_year["score_year"] == 2023].drop(columns=[TARGET]).copy()
    test.loc[test.index[:5], "material"] = "NEVER_SEEN"
    test.loc[test.index[5:10], "diameter_mm"] = np.nan
    scores = LogisticHazardRanker().fit(train).score(test)
    assert len(scores) == len(test)
    assert np.isfinite(scores).all()
