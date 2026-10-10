import json

import pandas as pd
import pytest

from src.modeling.config import CONTRACT_METHODS
from src.modeling.contracts import (
    metrics_consistency_errors,
    validate_fold_predictions,
    validate_metrics,
)
from src.modeling.evaluate import run_evaluation
from src.modeling.run_evaluation import main

TEST_YEARS = [2021, 2022, 2023]  # must match the evaluation fixture in conftest.py


def test_contract_b_is_valid(evaluation):
    assert validate_fold_predictions(evaluation.contract_b) == []


def test_contract_b_has_exactly_the_contract_methods(evaluation):
    assert set(evaluation.contract_b["method"]) == set(CONTRACT_METHODS)


def test_champion_rows_copy_the_winning_method(evaluation):
    champion = evaluation.metrics["champion_method"]
    cols = ["segment_id", "test_year", "model_score", "risk_percentile"]
    contract = evaluation.contract_b
    preds = evaluation.predictions
    champion_rows = contract[contract["method"] == "champion"][cols].sort_values(cols[:2]).reset_index(drop=True)
    source_rows = preds[preds["method"] == champion][cols].sort_values(cols[:2]).reset_index(drop=True)
    pd.testing.assert_frame_equal(champion_rows, source_rows)


def test_metrics_json_is_valid_strict_json(evaluation):
    assert validate_metrics(evaluation.metrics) == []
    json.dumps(evaluation.metrics, allow_nan=False)


def test_metrics_match_contract_b_exactly(evaluation):
    assert metrics_consistency_errors(evaluation.contract_b, evaluation.metrics) == []


def test_synthetic_runs_are_flagged(evaluation):
    assert evaluation.metrics["is_synthetic"] is True
    assert evaluation.metrics["limitations"][0].startswith("SYNTHETIC")


def test_rerun_with_fixed_seed_reproduces_artifacts(pipe_year, evaluation):
    again = run_evaluation(pipe_year, test_years=TEST_YEARS)
    pd.testing.assert_frame_equal(evaluation.contract_b, again.contract_b)

    def without_timestamp(metrics):
        return {k: v for k, v in metrics.items() if k != "generated_at"}

    assert without_timestamp(evaluation.metrics) == without_timestamp(again.metrics)


@pytest.mark.parametrize(
    "break_it, message",
    [
        (lambda df: df.drop(columns=["is_ood"]), "missing required column"),
        (lambda df: df.assign(method="xgboost"), "values outside"),
        (lambda df: df.assign(risk_percentile=1.5), "above maximum"),
        (lambda df: df.assign(confidence_label="SURE"), "values outside"),
        (lambda df: pd.concat([df, df.head(1)]), "duplicate"),
        (lambda df: df.assign(length_m=0.0), "must be >"),
        (lambda df: df[~((df["method"] == "random") & (df.index % 2 == 0))], "different segment sets"),
    ],
)
def test_validator_rejects_broken_frames(evaluation, break_it, message):
    errors = validate_fold_predictions(break_it(evaluation.contract_b))
    assert any(message in e for e in errors), errors


def test_cli_writes_artifacts_that_survive_a_parquet_round_trip(tmp_path):
    predictions = tmp_path / "fold_predictions.parquet"
    metrics = tmp_path / "metrics.json"
    code = main(
        [
            "--synthetic",
            "--synthetic-segments", "200",
            "--no-sensitivity",
            "--predictions-out", str(predictions),
            "--metrics-out", str(metrics),
        ]
    )
    assert code == 0
    frame = pd.read_parquet(predictions)
    assert validate_fold_predictions(frame) == []
    assert metrics_consistency_errors(frame, json.loads(metrics.read_text(encoding="utf-8"))) == []
