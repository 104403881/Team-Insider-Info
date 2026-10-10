"""Data-quality checks report counts and provenance labels stay honest."""

import pandas as pd

from jagapaip.loader import load_dataset
from jagapaip.quality import MISSING, PASS, WARN, field_validation_needs, provenance, run_checks


def by_name(rows):
    return {row["Check"]: row for row in rows}


def test_demo_dataset_is_labelled_synthetic(tmp_path):
    data = load_dataset(tmp_path)
    rows = provenance(data, "Screening heuristic")
    labels = {row["Element"]: row["Classification"] for row in rows}
    assert labels["Pipe attributes (material, install year, length)"] == "Synthetic demonstration data"
    assert labels["Risk scores"].startswith("Screening heuristic")
    assert labels["Evaluation metrics"].startswith("Missing")
    assert labels["Proof Mode comparison"].startswith("Simulated")
    assert labels["Worklist review marks"].startswith("Session-only")
    needs = field_validation_needs()
    assert len(needs) >= 4
    assert any("Dated break" in item["Requirement"] for item in needs)
    checks = by_name(run_checks(data))
    assert checks["Model predictions"]["Status"] == MISSING
    assert checks["Unique pipe IDs"]["Status"] == PASS


def test_problems_in_a_loaded_file_are_flagged(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pd.DataFrame(
        {
            "pipe_id": ["P1", "P1", "P2", "P3", "P3"],
            "year": [2019, 2020, 2020, 2019, 2020],
            "material": ["Cast Iron", "Cast Iron", None, "PVC", "PVC"],
            "install_year": [1960, 1960, None, 2015, 2015],
            "length_m": [100, 100, 9000, 80, 80],
            "breaks": [0, 1, 0, 1, 0],
        }
    ).to_csv(data_dir / "pipe_year.csv", index=False)
    pd.DataFrame({"pipe_id": ["P1", "P3"], "year": [2020, 2020], "predicted_risk": [0.4, 1.7]}).to_csv(
        data_dir / "fold_predictions.csv", index=False
    )
    data = load_dataset(tmp_path)
    assert data["meta"]["mode"] == "artifacts"
    checks = by_name(run_checks(data))
    assert checks["Install year present"]["Count"] == 1
    assert checks["Material recorded"]["Status"] == WARN
    assert checks["Segments over 5,000 m"]["Count"] == 1
    assert checks["Scores within 0 to 1"]["Count"] == 1
    assert checks["Prediction coverage, 2020"]["Count"] == 2
    labels = {row["Element"]: row["Classification"] for row in provenance(data, "Supplied predictions")}
    assert labels["Pipe attributes (material, install year, length)"].startswith("Observed data from file")
    assert labels["Proof Mode comparison"].startswith("Computed from loaded ledger")
