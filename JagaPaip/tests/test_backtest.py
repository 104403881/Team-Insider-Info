"""Proof Mode metrics: plans are fixed first, outcomes only score them."""

import pandas as pd
import pytest

from jagapaip.backtest import LeakageError, run_backtest
from jagapaip.demo_data import build_demo_tables
from jagapaip.proof import build_plan, compare_plans, complete_evaluation_years, network_as_of
from jagapaip.schema import STRATEGY_JAGAPAIP, STRATEGY_OLDEST


def toy():
    pipes = pd.DataFrame(
        {
            "pipe_id": ["A", "B", "C", "D", "LATE"],
            "material": ["Cast Iron", "PVC", "Ductile Iron", "PVC", "PVC"],
            "install_year": [1950, 1940, 1990, 2010, 2019],
            "length_m": [100.0, 100.0, 100.0, 700.0, 50.0],
        }
    )
    breaks = pd.DataFrame(
        {
            "pipe_id": ["A", "A", "A", "B", "C", "LATE"],
            "break_year": [2010, 2017, 2018, 2019, 2017, 2019],
            "break_count": [1, 1, 1, 1, 2, 1],
        }
    )
    return pipes, breaks


def test_capture_rates_follow_the_documented_definition():
    pipes, breaks = toy()
    features = network_as_of(pipes, breaks, 2016)
    result = run_backtest(features, breaks, 2016, budget_m=100, horizon=3, capture_fraction=0.10)
    assert result["eligible_segments"] == 4
    assert result["eligible_length_m"] == 1000
    assert result["eligible_breaks"] == 5
    assert result["excluded_breaks"] == 1
    assert result["window"] == (2017, 2019)
    ours = result["at_budget"][STRATEGY_JAGAPAIP]
    base = result["at_budget"][STRATEGY_OLDEST]
    assert ours["segments"] == 1 and base["segments"] == 1
    assert base["captured_breaks"] == 1
    assert base["capture_rate"] == pytest.approx(1 / 5)
    assert ours["capture_rate"] == pytest.approx(ours["captured_breaks"] / 5)
    assert result["capture_budget_m"] == pytest.approx(100)


def test_plans_are_identical_whatever_the_outcomes():
    pipes, breaks = toy()
    features = network_as_of(pipes, breaks, 2016)
    altered = breaks.copy()
    altered.loc[altered["break_year"] > 2016, "break_count"] = 50
    first = run_backtest(features, breaks, 2016, budget_m=200)
    second = run_backtest(features, altered, 2016, budget_m=200)
    for group in ("budget", "capture"):
        for strategy in (STRATEGY_JAGAPAIP, STRATEGY_OLDEST):
            a = first["plans"][group][strategy]
            b = second["plans"][group][strategy]
            assert a["pipe_id"].tolist() == b["pipe_id"].tolist()
            assert a["selected"].tolist() == b["selected"].tolist()
    assert first["eligible_breaks"] != second["eligible_breaks"]


def test_backtest_plan_matches_the_plan_shown_before_reveal():
    pipes, breaks = build_demo_tables()
    year = complete_evaluation_years(pipes, breaks)[-1]
    features = network_as_of(pipes, breaks, year)
    shown = build_plan(features, 1500, STRATEGY_JAGAPAIP)
    result = run_backtest(features, breaks, year, 1500)
    inside = result["plans"]["budget"][STRATEGY_JAGAPAIP]
    assert inside.loc[inside["selected"], "pipe_id"].tolist() == shown.loc[shown["selected"], "pipe_id"].tolist()


def test_feature_table_with_outcome_columns_is_rejected():
    pipes, breaks = toy()
    features = network_as_of(pipes, breaks, 2016)
    features["future_breaks"] = 1
    with pytest.raises(LeakageError):
        run_backtest(features, breaks, 2016, budget_m=100)


def test_empty_window_reports_unavailable_rates():
    pipes, breaks = toy()
    features = network_as_of(pipes, breaks, 2016)
    quiet = breaks.loc[breaks["break_year"] <= 2016]
    result = run_backtest(features, quiet, 2016, budget_m=100)
    assert result["eligible_breaks"] == 0
    assert result["at_budget"][STRATEGY_JAGAPAIP]["capture_rate"] is None
    assert result["lift_at_capture"] is None


def test_compare_plans_uses_the_same_budget_and_does_not_read_outcomes():
    pipes, breaks = toy()
    features = network_as_of(pipes, breaks, 2016)
    jagapaip = build_plan(features, 200, STRATEGY_JAGAPAIP)
    baseline = build_plan(features, 200, STRATEGY_OLDEST)
    first = compare_plans(jagapaip, baseline, 200)
    altered = breaks.copy()
    altered.loc[altered["break_year"] > 2016, "break_count"] = 50
    # Rebuilding from the same features keeps the plans identical; outcomes never enter compare_plans.
    second = compare_plans(jagapaip, baseline, 200)
    assert first == second
    assert first["budget_m"] == 200
    assert first["jagapaip"]["length_m"] <= 200 + 1e-6
    assert first["oldest_first"]["length_m"] <= 200 + 1e-6
    selected_ours = set(jagapaip.loc[jagapaip["selected"], "pipe_id"])
    selected_base = set(baseline.loc[baseline["selected"], "pipe_id"])
    assert set(first["overlap_ids"]) == {str(item) for item in selected_ours & selected_base}
    assert first["jagapaip"]["high_risk_selected"] <= first["jagapaip"]["high_risk_in_network"]
    # Score mass uses the ranking scores already on the plan. JagaPaip should not lose on that number.
    assert first["jagapaip"]["score_sum"] + 1e-9 >= first["oldest_first"]["score_sum"]


def test_capture_budget_never_exceeded():
    pipes, breaks = build_demo_tables()
    year = complete_evaluation_years(pipes, breaks)[0]
    features = network_as_of(pipes, breaks, year)
    result = run_backtest(features, breaks, year, budget_m=750)
    for strategy in (STRATEGY_JAGAPAIP, STRATEGY_OLDEST):
        assert result["at_capture"][strategy]["length_m"] <= result["capture_budget_m"] + 1e-6
        assert result["at_budget"][strategy]["length_m"] <= 750 + 1e-6
