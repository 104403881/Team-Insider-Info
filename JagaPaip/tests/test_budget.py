"""Budget selection changes the pipes, not only a displayed total."""

import pandas as pd
import pytest

from jagapaip.ranking import RankingError, build_worklist
from jagapaip.schema import STRATEGY_OLDEST


def network() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pipe_id": ["A", "B", "C", "D"],
            "length_m": [100.0, 100.0, 50.0, 1000.0],
            "predicted_risk": [0.90, 0.80, 0.70, 0.95],
            "age_years": [10, 80, 30, 20],
            "install_year": [2000, 1940, 1990, 2005],
            "historical_breaks": [0, 3, 1, 0],
            "material": ["PVC", "Cast Iron", "Ductile Iron", "PVC"],
            "decision_year": [2020, 2020, 2020, 2020],
        }
    )


def selected_ids(plan: pd.DataFrame) -> list[str]:
    return plan.loc[plan["selected"], "pipe_id"].astype(str).tolist()


def test_budget_skips_a_segment_that_does_not_fit() -> None:
    plan = build_worklist(network(), budget_m=150)
    assert selected_ids(plan) == ["A", "C"]
    assert plan.loc[plan["pipe_id"] == "D", "selection_reason"].iloc[0].endswith(
        "longer than the remaining length budget"
    )
    assert float(plan.loc[plan["selected"], "length_m"].sum()) <= 150


def test_changing_the_budget_changes_the_selected_pipes() -> None:
    tight = selected_ids(build_worklist(network(), budget_m=100))
    wider = selected_ids(build_worklist(network(), budget_m=200))
    assert tight == ["A"]
    assert wider == ["A", "B"]
    assert tight != wider


def test_zero_budget_selects_nothing_and_full_budget_respects_order() -> None:
    assert selected_ids(build_worklist(network(), budget_m=0)) == []
    full = build_worklist(network(), budget_m=10_000)
    assert selected_ids(full) == ["D", "A", "B", "C"]
    assert float(full.loc[full["selected"], "length_m"].sum()) == 1250


def test_missing_length_is_not_eligible() -> None:
    frame = network()
    frame.loc[frame["pipe_id"] == "A", "length_m"] = pd.NA
    plan = build_worklist(frame, budget_m=150)
    assert "A" not in selected_ids(plan)
    reason = plan.loc[plan["pipe_id"] == "A", "selection_reason"].iloc[0]
    assert "missing" in reason


def test_negative_budget_is_rejected() -> None:
    with pytest.raises(RankingError):
        build_worklist(network(), budget_m=-1)


def test_oldest_first_uses_install_year_not_risk() -> None:
    plan = build_worklist(network(), budget_m=150, strategy=STRATEGY_OLDEST)
    assert selected_ids(plan) == ["B", "C"]

    reversed_risk = network()
    reversed_risk["predicted_risk"] = [0.1, 0.1, 0.1, 0.99]
    again = build_worklist(reversed_risk, budget_m=150, strategy=STRATEGY_OLDEST)
    assert selected_ids(again) == ["B", "C"]
