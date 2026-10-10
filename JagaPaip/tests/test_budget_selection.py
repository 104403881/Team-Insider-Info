"""Length-budget selection: the funded set depends on lengths, not a fixed label."""

import pandas as pd
import pytest

from jagapaip.ranking import RankingError, apply_length_budget, build_worklist, plan_summary


def _features():
    return pd.DataFrame(
        [
            {"pipe_id": "A", "material": "PVC", "install_year": 2000, "length_m": 500.0, "age_years": 10, "historical_breaks": 0, "predicted_risk": 0.90, "decision_year": 2020},
            {"pipe_id": "B", "material": "PVC", "install_year": 2001, "length_m": 80.0, "age_years": 10, "historical_breaks": 0, "predicted_risk": 0.70, "decision_year": 2020},
            {"pipe_id": "C", "material": "PVC", "install_year": 2002, "length_m": 50.0, "age_years": 10, "historical_breaks": 0, "predicted_risk": 0.40, "decision_year": 2020},
            {"pipe_id": "D", "material": "PVC", "install_year": 2003, "length_m": 40.0, "age_years": 10, "historical_breaks": 0, "predicted_risk": 0.20, "decision_year": 2020},
        ]
    )


def _selected(plan: pd.DataFrame) -> list[str]:
    return plan.loc[plan["selected"], "pipe_id"].tolist()


def test_budget_skips_a_segment_that_does_not_fit_and_takes_a_shorter_one():
    plan = build_worklist(_features(), budget_m=120)
    # A is first but too long. B uses 80 m. C is 50 m and does not fit in the
    # remaining 40 m, so it is skipped and the shorter D is funded.
    assert _selected(plan) == ["B", "D"]
    reason = plan.loc[plan["pipe_id"] == "A", "selection_reason"].iloc[0]
    assert reason == "Not selected - longer than the remaining length budget"
    assert plan.loc[plan["selected"], "length_m"].sum() <= 120


def test_zero_budget_selects_nothing():
    plan = build_worklist(_features(), budget_m=0)
    assert _selected(plan) == []
    assert plan_summary(plan, 0)["selected_m"] == 0


def test_negative_budget_is_rejected():
    with pytest.raises(RankingError):
        build_worklist(_features(), budget_m=-1)


def test_larger_budget_funds_more_length():
    small = build_worklist(_features(), budget_m=80)
    large = build_worklist(_features(), budget_m=180)
    assert plan_summary(small, 80)["selected_m"] < plan_summary(large, 180)["selected_m"]
    assert _selected(small) == ["B"]
    assert _selected(large) == ["B", "C", "D"]


def test_selected_length_never_exceeds_budget():
    for budget in (0, 40, 90, 130, 500, 1000):
        plan = build_worklist(_features(), budget_m=budget)
        funded = float(plan.loc[plan["selected"], "length_m"].sum())
        assert funded <= budget + 1e-6


def test_apply_length_budget_uses_the_order_it_is_given():
    ordered = _features().sort_values("pipe_id", ascending=False)
    plan = apply_length_budget(ordered, budget_m=90)
    assert _selected(plan) == ["D", "C"]
    assert plan["rank"].tolist() == [1, 2, 3, 4]
