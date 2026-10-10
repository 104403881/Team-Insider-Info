"""Future breaks can be counted after a plan exists. They cannot build the plan."""

import inspect

import pandas as pd

from jagapaip.demo_data import build_demo_tables
from jagapaip.loader import load_dataset
from jagapaip.proof import (
    attach_predictions,
    build_plan,
    complete_evaluation_years,
    network_as_of,
    outcome_counts,
)
from jagapaip.ranking import build_worklist
from jagapaip.schema import PROOF_HORIZON_YEARS, STRATEGY_JAGAPAIP


def test_build_plan_has_no_outcome_argument() -> None:
    parameters = inspect.signature(build_plan).parameters
    assert "breaks" not in parameters
    assert "outcomes" not in parameters
    assert "future_breaks" not in parameters


def test_future_column_does_not_change_the_worklist() -> None:
    pipes, breaks = build_demo_tables()
    features = network_as_of(pipes, breaks, 2018)
    clean = build_worklist(features, budget_m=2_000, strategy=STRATEGY_JAGAPAIP)
    dirty = features.copy()
    dirty["future_breaks"] = range(len(dirty), 0, -1)
    contaminated = build_worklist(dirty, budget_m=2_000, strategy=STRATEGY_JAGAPAIP)
    assert "future_breaks" not in contaminated.columns
    assert clean.loc[clean["selected"], "pipe_id"].tolist() == contaminated.loc[
        contaminated["selected"], "pipe_id"
    ].tolist()


def test_breaks_after_the_decision_year_are_excluded_from_history() -> None:
    pipes, breaks = build_demo_tables()
    year = 2018
    history = network_as_of(pipes, breaks, year)
    altered = breaks.copy()
    altered.loc[altered["break_year"] > year, "break_count"] = 99
    again = network_as_of(pipes, altered, year)
    pd.testing.assert_series_equal(
        history["historical_breaks"].reset_index(drop=True),
        again["historical_breaks"].reset_index(drop=True),
    )
    outcomes = outcome_counts(breaks, year)
    assert outcomes.empty or int(outcomes["future_breaks"].sum()) >= 0
    leaked = breaks.loc[breaks["break_year"] <= year, "break_count"].sum()
    assert int(history["historical_breaks"].sum()) == int(leaked)


def test_prediction_from_a_later_year_is_not_used() -> None:
    pipes, breaks = build_demo_tables()
    pipe_id = str(pipes.iloc[0]["pipe_id"])
    predictions = pd.DataFrame(
        {
            "pipe_id": [pipe_id, pipe_id],
            "year": [2018, 2020],
            "predicted_risk": [0.15, 0.99],
        }
    )
    features = attach_predictions(network_as_of(pipes, breaks, 2018), predictions, 2018)
    score = float(features.loc[features["pipe_id"] == pipe_id, "predicted_risk"].iloc[0])
    assert score == 0.15


def test_demo_proof_years_end_before_the_outcome_window() -> None:
    pipes, breaks = build_demo_tables()
    years = complete_evaluation_years(pipes, breaks)
    assert years
    assert max(years) <= int(breaks["break_year"].max()) - PROOF_HORIZON_YEARS


def test_missing_files_are_a_labelled_demo(tmp_path) -> None:
    loaded = load_dataset(tmp_path)
    assert loaded["meta"]["mode"] == "demo"
    assert "DEMO DATA" in loaded["meta"]["status_title"]
    assert loaded["metrics"] is None


def test_pipe_year_csv_holds_future_breaks_out_of_the_decision_table(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pd.DataFrame(
        {
            "pipe_id": ["P1", "P1", "P1", "P2", "P2", "P2"],
            "year": [2019, 2020, 2021, 2019, 2020, 2021],
            "material": ["Cast Iron", "Cast Iron", "Cast Iron", "PVC", "PVC", "PVC"],
            "install_year": [1960, 1960, 1960, 2010, 2010, 2010],
            "length_m": [100, 100, 100, 80, 80, 80],
            "breaks": [1, 0, 4, 0, 0, 1],
        }
    ).to_csv(data_dir / "pipe_year.csv", index=False)

    loaded = load_dataset(tmp_path)
    assert loaded["meta"]["mode"] == "artifacts"
    features = network_as_of(loaded["pipes"], loaded["breaks"], 2019)
    p1_history = int(features.loc[features["pipe_id"] == "P1", "historical_breaks"].iloc[0])
    assert p1_history == 1
    outcomes = outcome_counts(loaded["breaks"], 2019, horizon=2)
    p1_future = int(outcomes.loc[outcomes["pipe_id"] == "P1", "future_breaks"].iloc[0])
    assert p1_future == 4
    plan = build_plan(features, budget_m=100)
    assert "future_breaks" not in plan.columns


def test_cumulative_break_totals_are_not_summed_as_events(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pd.DataFrame(
        {
            "pipe_id": ["P1"] * 4,
            "year": [2018, 2019, 2020, 2021],
            "material": ["Cast Iron"] * 4,
            "install_year": [1950] * 4,
            "length_m": [120] * 4,
            "breaks": [1, 1, 3, 3],
        }
    ).to_csv(data_dir / "pipe_year.csv", index=False)
    loaded = load_dataset(tmp_path)
    features = network_as_of(loaded["pipes"], loaded["breaks"], 2019)
    assert int(features.loc[features["pipe_id"] == "P1", "historical_breaks"].iloc[0]) == 1
    outcomes = outcome_counts(loaded["breaks"], 2019, horizon=2)
    assert int(outcomes.loc[outcomes["pipe_id"] == "P1", "future_breaks"].iloc[0]) == 2
