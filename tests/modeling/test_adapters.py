import json
from pathlib import Path

import pandas as pd
import pytest

from src.modeling.adapters import adapt_member1_pipe_year, load_member1_package
from src.modeling.contracts import validate_pipe_year

MEMBER1_PACKAGE = Path(__file__).resolve().parents[2] / "data"


def member1_rows():
    """A few rows in Member 1's layout (data/data_dictionary.md)."""
    return pd.DataFrame(
        {
            "segment_id": [101, 101, 102, 103],
            "year": pd.array([1999, 2005, 2005, 2005], dtype="int16"),
            "installation_year": pd.array([1960, 1960, 1990, 1950], dtype="Int64"),
            "age_years": pd.array([39, 45, 15, 55], dtype="int16"),
            "material": ["CI", "CI", "UNKNOWN", "DI"],
            "pipe_size_mm": [150.0, 150.0, None, 200.0],
            "length_m": [120.5, 120.5, 80.0, 45.2],
            "prior_break_count": pd.array([0, 2, 0, 1], dtype="int16"),
            "years_since_last_break": [None, 1.4, None, 6.0],
            "material_unknown": [False, False, True, False],
            "pipe_size_missing": [False, False, True, False],
            "ambiguous_asset_history": [False, False, False, True],
            "eligible_inventory": [True, True, True, True],
            "target_next_year_break": pd.array([0, 1, 0, 0], dtype="int8"),
        }
    )


def test_adapted_rows_pass_contract_a():
    adapted = adapt_member1_pipe_year(member1_rows(), "2026-10-10", first_score_year=1990)
    report = validate_pipe_year(adapted)
    assert report.errors == []
    assert adapted["segment_id"].tolist() == ["101", "101", "102", "103"]
    assert set(adapted["source_snapshot_date"]) == {"2026-10-10"}


def test_quality_flags_come_from_member1_qa_columns():
    adapted = adapt_member1_pipe_year(member1_rows(), "2026-10-10", first_score_year=1990)
    flags = adapted["data_quality_flags"].map(json.loads).tolist()
    assert flags == [[], [], ["UNKNOWN_MATERIAL", "MISSING_DIAMETER"], ["BREAK_BEFORE_INSTALL"]]
    assert adapted["is_ambiguous_history"].tolist() == [False, False, False, True]


def test_burn_in_years_and_ineligible_rows_are_dropped():
    rows = member1_rows()
    rows.loc[2, "eligible_inventory"] = False
    adapted = adapt_member1_pipe_year(rows, "2026-10-10", first_score_year=2000)
    assert adapted["score_year"].tolist() == [2005, 2005]
    assert adapted["segment_id"].tolist() == ["101", "103"]


@pytest.mark.skipif(not (MEMBER1_PACKAGE / "manifest.json").exists(), reason="Member 1 package not present")
def test_real_member1_package_passes_contract_a():
    adapted = load_member1_package(MEMBER1_PACKAGE)
    report = validate_pipe_year(adapted)
    assert report.errors == []
    assert report.warnings == []
    assert adapted["score_year"].min() == 2000
    assert adapted["score_year"].max() == 2025
