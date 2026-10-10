"""Ranking uses decision-year scores and fixed action bands."""

import pandas as pd

from jagapaip.ranking import action_for_score, band_for_score, build_worklist
from jagapaip.schema import (
    ACTION_INSPECT,
    ACTION_MONITOR,
    ACTION_RENEWAL,
    BAND_HIGH,
    BAND_LOW,
    BAND_MODERATE,
    STRATEGY_JAGAPAIP,
    STRATEGY_OLDEST,
)


def test_action_bands_follow_the_published_thresholds() -> None:
    assert action_for_score(0.70) == ACTION_RENEWAL
    assert band_for_score(0.70) == BAND_HIGH
    assert action_for_score(0.699) == ACTION_INSPECT
    assert action_for_score(0.45) == ACTION_INSPECT
    assert band_for_score(0.45) == BAND_MODERATE
    assert action_for_score(0.449) == ACTION_MONITOR
    assert band_for_score(0.449) == BAND_LOW


def test_risk_rank_puts_the_higher_score_first() -> None:
    frame = pd.DataFrame(
        {
            "pipe_id": ["low", "high"],
            "length_m": [10.0, 10.0],
            "predicted_risk": [0.2, 0.9],
            "age_years": [80, 5],
            "install_year": [1940, 2015],
            "historical_breaks": [4, 0],
            "material": ["Cast Iron", "PVC"],
            "decision_year": [2020, 2020],
        }
    )
    plan = build_worklist(frame, budget_m=10, strategy=STRATEGY_JAGAPAIP)
    assert plan.iloc[0]["pipe_id"] == "high"
    assert plan.iloc[0]["recommended_action"] == ACTION_RENEWAL
    assert "caused a break" in plan.iloc[0]["explanation"]
    assert "not a finding" in plan.iloc[0]["explanation"]


def test_oldest_order_ignores_the_risk_score() -> None:
    frame = pd.DataFrame(
        {
            "pipe_id": ["new", "old"],
            "length_m": [10.0, 10.0],
            "predicted_risk": [0.99, 0.01],
            "install_year": [2010, 1950],
            "age_years": [10, 70],
            "historical_breaks": [0, 0],
            "material": ["PVC", "PVC"],
            "decision_year": [2020, 2020],
        }
    )
    plan = build_worklist(frame, budget_m=10, strategy=STRATEGY_OLDEST)
    assert plan.iloc[0]["pipe_id"] == "old"


def test_missing_break_history_is_not_described_as_zero() -> None:
    frame = pd.DataFrame(
        {
            "pipe_id": ["P"],
            "length_m": [40.0],
            "age_years": [40],
            "install_year": [1980],
            "material": ["PVC"],
            "historical_breaks": [pd.NA],
            "decision_year": [2020],
        }
    )
    plan = build_worklist(frame, budget_m=40)
    text = plan.iloc[0]["explanation"]
    assert "not in the source" in text
    assert "0 on or before" not in text
