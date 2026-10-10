"""Future break outcomes must not change ranking or the funded plan."""

import inspect

import pandas as pd

from jagapaip import ranking
from jagapaip.proof import attach_predictions, build_plan, capture_summary, network_as_of, outcome_counts
from jagapaip.ranking import build_worklist
from jagapaip.schema import FEATURE_COLUMNS, STRATEGY_JAGAPAIP


def _network():
    pipes = pd.DataFrame(
        {
            "pipe_id": ["A", "B", "C"],
            "zone": ["North feeder", "Central grid", "South feeder"],
            "material": ["Cast Iron", "PVC", "Ductile Iron"],
            "install_year": [1960, 2010, 1990],
            "length_m": [120.0, 80.0, 100.0],
            "diameter_mm": [150, 100, 200],
        }
    )
    breaks = pd.DataFrame(
        {
            "pipe_id": ["A", "A", "A", "B", "C"],
            "break_year": [2010, 2015, 2018, 2019, 2012],
            "break_count": [1, 1, 1, 1, 1],
        }
    )
    return pipes, breaks


def test_feature_snapshot_excludes_breaks_after_the_decision_year():
    pipes, breaks = _network()
    features = network_as_of(pipes, breaks, decision_year=2016)
    assert list(features.columns) == FEATURE_COLUMNS
    counts = features.set_index("pipe_id")["historical_breaks"].to_dict()
    assert counts == {"A": 2, "B": 0, "C": 1}
    assert "future_breaks" not in features.columns


def test_changing_future_breaks_does_not_change_the_plan():
    pipes, breaks = _network()
    features = network_as_of(pipes, breaks, 2016)
    original = build_plan(features, budget_m=200, strategy=STRATEGY_JAGAPAIP)

    future = breaks["break_year"] > 2016
    without_future = breaks.loc[~future].copy()
    features_without = network_as_of(pipes, without_future, 2016)
    rebuilt = build_plan(features_without, budget_m=200, strategy=STRATEGY_JAGAPAIP)

    assert original["pipe_id"].tolist() == rebuilt["pipe_id"].tolist()
    assert original["predicted_risk"].tolist() == rebuilt["predicted_risk"].tolist()
    assert original["selected"].tolist() == rebuilt["selected"].tolist()

    poisoned = features.copy()
    poisoned["future_breaks"] = [50, 0, 0]
    poisoned["y_true"] = [9, 0, 1]
    from_poison = build_plan(poisoned, budget_m=200, strategy=STRATEGY_JAGAPAIP)
    assert from_poison["pipe_id"].tolist() == original["pipe_id"].tolist()
    assert from_poison["selected"].tolist() == original["selected"].tolist()
    assert "future_breaks" not in from_poison.columns
    assert "y_true" not in from_poison.columns


def test_reveal_metrics_do_change_when_future_breaks_change():
    pipes, breaks = _network()
    features = network_as_of(pipes, breaks, 2016)
    plan = build_plan(features, budget_m=1000, strategy=STRATEGY_JAGAPAIP)
    before = capture_summary(plan, outcome_counts(breaks, 2016, horizon=3))
    after = capture_summary(plan, outcome_counts(breaks.loc[breaks["break_year"] <= 2016], 2016, horizon=3))
    assert before["captured_breaks"] > after["captured_breaks"]
    assert before["segments_selected"] == after["segments_selected"]


def test_supplied_score_beats_an_outcome_column():
    frame = pd.DataFrame(
        [
            {
                "pipe_id": "A",
                "material": "PVC",
                "install_year": 2000,
                "length_m": 100.0,
                "age_years": 10,
                "historical_breaks": 0,
                "predicted_risk": 0.15,
                "y_true": 40,
                "future_breaks": 40,
            },
            {
                "pipe_id": "B",
                "material": "PVC",
                "install_year": 2000,
                "length_m": 100.0,
                "age_years": 10,
                "historical_breaks": 0,
                "predicted_risk": 0.85,
                "y_true": 0,
                "future_breaks": 0,
            },
        ]
    )
    plan = build_worklist(frame, budget_m=100)
    assert plan.loc[plan["selected"], "pipe_id"].tolist() == ["B"]


def test_prediction_file_attaches_only_the_score():
    pipes, breaks = _network()
    features = network_as_of(pipes, breaks, 2016)
    predictions = pd.DataFrame(
        {
            "pipe_id": ["A", "B", "C"],
            "year": [2016, 2016, 2016],
            "predicted_risk": [0.2, 0.9, 0.4],
            "y_true": [5, 0, 2],
        }
    )
    attached = attach_predictions(features, predictions, 2016)
    assert "y_true" not in attached.columns
    plan = build_plan(attached, budget_m=80)
    assert plan.iloc[0]["pipe_id"] == "B"
    assert plan.iloc[0]["predicted_risk"] == 0.9


def test_ranking_module_does_not_reference_outcome_logic():
    source = inspect.getsource(ranking)
    assert "break_year" not in source
    assert "outcome_counts" not in source
    assert "future_breaks" not in source
