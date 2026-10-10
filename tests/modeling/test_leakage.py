"""Definition of done: every score is produced using only prior-year information."""

import numpy as np
import pandas as pd

from src.modeling.config import TARGET
from src.modeling.evaluate import predict_walk_forward, prepare_panel
from src.modeling.methods import Ranker

SCORE_COLUMNS = ["method", "segment_id", "model_score", "risk_percentile", "confidence_label", "is_ood"]


class SpyRanker(Ranker):
    name = "spy"
    calls: list = []

    def fit(self, train):
        SpyRanker.calls.append(("fit", sorted(train["score_year"].unique())))
        return self

    def score(self, test):
        SpyRanker.calls.append(("score", sorted(test["score_year"].unique()), TARGET in test.columns))
        return np.zeros(len(test))


def _scores(predictions, year):
    rows = predictions[predictions["test_year"] == year]
    return rows.sort_values(["method", "segment_id"])[SCORE_COLUMNS].reset_index(drop=True)


def test_rankers_see_only_prior_years_and_never_the_test_target(pipe_year):
    SpyRanker.calls = []
    predict_walk_forward(prepare_panel(pipe_year), [2021, 2022], rankers={"spy": SpyRanker})
    fits = [c for c in SpyRanker.calls if c[0] == "fit"]
    scores = [c for c in SpyRanker.calls if c[0] == "score"]
    assert len(fits) == len(scores) == 2
    for (_, train_years), (_, test_years, saw_target) in zip(fits, scores):
        assert len(test_years) == 1
        assert max(train_years) < test_years[0]
        assert not saw_target


def test_test_year_outcomes_cannot_change_test_year_scores(pipe_year):
    panel = prepare_panel(pipe_year)
    poisoned = panel.copy()
    in_test = poisoned["score_year"] == 2022
    poisoned.loc[in_test, TARGET] = 1 - poisoned.loc[in_test, TARGET]
    pd.testing.assert_frame_equal(
        _scores(predict_walk_forward(panel, [2022]), 2022),
        _scores(predict_walk_forward(poisoned, [2022]), 2022),
    )


def test_future_years_cannot_change_earlier_scores(pipe_year):
    panel = prepare_panel(pipe_year)
    poisoned = panel.copy()
    future = poisoned["score_year"] > 2021
    poisoned.loc[future, TARGET] = 1
    poisoned.loc[future, "prior_break_count"] = 99
    pd.testing.assert_frame_equal(
        _scores(predict_walk_forward(panel, [2021]), 2021),
        _scores(predict_walk_forward(poisoned, [2021]), 2021),
    )
