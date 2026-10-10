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


def test_budget_stops_at_the_first_overflow_instead_of_skipping_ahead():
    # Order A (500 m), B (80 m), C (50 m), D (40 m). With 625 m, A and B fit (580 m);
    # C overflows, so the list stops even though D would still fit in the 45 m left.
    plan = build_worklist(_features(), budget_m=625)
    assert _selected(plan) == ["A", "B"]
    assert plan.loc[plan["pipe_id"] == "C", "selection_reason"].iloc[0] == "Not selected - longer than the remaining length budget"
    assert plan.loc[plan["pipe_id"] == "D", "selection_reason"].iloc[0] == "Not selected - the list stopped at an earlier segment that did not fit"
    assert plan.loc[plan["selected"], "length_m"].sum() <= 625


def test_a_first_segment_longer_than_the_budget_selects_nothing():
    plan = build_worklist(_features(), budget_m=120)
    assert _selected(plan) == []
    assert plan.loc[plan["pipe_id"] == "A", "selection_reason"].iloc[0] == "Not selected - longer than the remaining length budget"


def test_zero_budget_selects_nothing():
    plan = build_worklist(_features(), budget_m=0)
    assert _selected(plan) == []
    assert plan_summary(plan, 0)["selected_m"] == 0


def test_negative_budget_is_rejected():
    with pytest.raises(RankingError):
        build_worklist(_features(), budget_m=-1)


def test_larger_budget_funds_more_length():
    small = build_worklist(_features(), budget_m=500)
    large = build_worklist(_features(), budget_m=580)
    assert plan_summary(small, 500)["selected_m"] < plan_summary(large, 580)["selected_m"]
    assert _selected(small) == ["A"]
    assert _selected(large) == ["A", "B"]


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
