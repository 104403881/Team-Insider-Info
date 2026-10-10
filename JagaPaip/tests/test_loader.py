"""Missing artifacts fall back to the labelled demo. Present files are read as themselves."""

import json

import pandas as pd
import pytest

from pathlib import Path

from jagapaip.loader import interpret_pipe_table, interpret_predictions, load_dataset
from jagapaip.proof import features_for_year


def test_missing_files_load_the_demo(tmp_path):
    data = load_dataset(tmp_path)
    assert data["meta"]["mode"] == "demo"
    assert data["meta"]["status_title"] == "DEMO DATA — NOT REAL UTILITY DATA"
    assert len(data["pipes"]) > 0
    assert data["breaks"] is not None
    assert data["metrics"] is None


def test_pipe_year_and_metrics_are_used_when_present(tmp_path):
    table = pd.DataFrame(
        {
            "segment_id": ["P1", "P1", "P2"],
            "year": [2018, 2019, 2019],
            "material": ["PVC", "PVC", "Cast Iron"],
            "install_year": [2001, 2001, 1970],
            "length": [110.0, 110.0, 80.0],
            "breaks": [0, 1, 2],
        }
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    table.to_parquet(data_dir / "pipe_year.parquet", index=False)
    (data_dir / "metrics.json").write_text(json.dumps({"horizon_years": 3, "note": "reported by the file"}), encoding="utf-8")

    data = load_dataset(tmp_path)
    assert data["meta"]["mode"] == "artifacts"
    assert set(data["pipes"]["pipe_id"]) == {"P1", "P2"}
    assert data["meta"]["decision_year"] == 2019
    ledger = data["breaks"]
    assert int(ledger.loc[ledger["pipe_id"] == "P1", "break_count"].sum()) == 1
    assert data["metrics"]["horizon_years"] == 3


def test_prediction_adapter_drops_outcome_columns():
    frame = pd.DataFrame(
        {
            "pipe_id": ["A", "A"],
            "fold": [1, 2],
            "year": [2016, 2016],
            "y_pred": [0.2, 0.4],
            "y_true": [1, 0],
        }
    )
    predictions, warnings = interpret_predictions(frame)
    assert list(predictions.columns) == ["pipe_id", "year", "predicted_risk"]
    assert predictions.iloc[0]["predicted_risk"] == pytest.approx(0.3)
    assert any("folds" in warning for warning in warnings)


def test_target_columns_are_not_used_as_history(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pd.DataFrame(
        {
            "segment_id": ["A", "A"],
            "year": [2018, 2019],
            "installation_year": [2000, 2000],
            "length_m": [100.0, 100.0],
            "material": ["CI", "CI"],
            "pipe_size_mm": [150.0, 150.0],
            "prior_break_count": [0, 1],
            "target_break_count": [1, 0],
            "target_next_year_break": [1, 0],
        }
    ).to_parquet(data_dir / "pipe_year.parquet", index=False)
    pd.DataFrame({"segment_id": ["A"], "incident_id": [9], "incident_year": [2018]}).to_parquet(
        data_dir / "breaks_clean.parquet", index=False
    )
    data = load_dataset(tmp_path)
    assert data["meta"]["mode"] == "artifacts"
    assert set(data["breaks"]["break_year"]) == {2018}
    features = features_for_year(data, 2019)
    assert "target_break_count" not in features.columns
    assert "target_next_year_break" not in features.columns
    assert int(features.iloc[0]["historical_breaks"]) == 1
    assert float(features.iloc[0]["diameter_mm"]) == 150


def test_project_folder_loads_member1_kitchener_files():
    data = load_dataset(Path(__file__).resolve().parent.parent)
    assert data["meta"]["mode"] == "artifacts"
    assert data["meta"]["demonstrator"] is True
    assert len(data["pipes"]) > 1000
    assert data["breaks"] is not None and len(data["breaks"]) > 0
    assert data["panel"] is not None
    features = features_for_year(data, int(data["meta"]["decision_year"]))
    assert "target_break_count" not in features.columns
    assert len(features) > 1000


def test_yearless_break_total_disables_a_future_window():
    pipes, breaks, warnings, snapshot = interpret_pipe_table(
        pd.DataFrame({"pipe_id": ["A"], "length_m": [50.0], "install_year": [1990], "break_count": [4]})
    )
    assert breaks is None
    assert snapshot is None
    assert pipes.iloc[0]["historical_breaks"] == 4
    assert any("no year" in warning for warning in warnings)
