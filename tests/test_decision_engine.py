
import pandas as pd
import pytest

from src.decision_engine import (
    build_ranked_worklist,
    renewal_review_eligible,
)


@pytest.fixture
def predictions():
    return pd.DataFrame({
        "segment_id": ["P003", "P002", "P001", "P004"],
        "test_year": [2025, 2025, 2025, 2025],
        "method": [
            "champion", "champion", "champion", "oldest"
        ],
        "model_score": [0.7, 0.6, 0.5, 0.2],
        "risk_percentile": [0.8, 0.9, 0.9, 0.1],
        "confidence_label": [
            "HIGH", "MEDIUM", "HIGH", "HIGH"
        ],
        "is_ood": [False, False, False, False],
        "actual_break": [0, 0, 1, 0],
        "length_m": [40.0, 20.0, 30.0, 10.0],
    })


def test_ranking_and_tie_breaking(predictions):
    result = build_ranked_worklist(
        predictions, 2025, 1.0
    )

    assert result["segment_id"].tolist() == [
        "P001", "P002", "P003"
    ]


def test_prefix_budget_selection(predictions):
    result = build_ranked_worklist(
        predictions, 2025, 0.55
    )

    # Champion total length = 90m.
    # Budget = 49.5m.
    # P001 = 30m; adding P002 would exceed budget.
    assert result["selected"].tolist() == [
        True, False, False
    ]


def test_zero_budget(predictions):
    result = build_ranked_worklist(
        predictions, 2025, 0.0
    )

    assert not result["selected"].any()


def test_full_budget(predictions):
    result = build_ranked_worklist(
        predictions, 2025, 1.0
    )

    assert result["selected"].all()


def test_low_confidence_blocked_from_renewal(predictions):
    row = predictions.iloc[0].copy()
    row["confidence_label"] = "LOW"
    row["is_ood"] = False

    assert renewal_review_eligible(row) is False


def test_ood_blocked_from_renewal(predictions):
    row = predictions.iloc[0].copy()
    row["confidence_label"] = "HIGH"
    row["is_ood"] = True

    assert renewal_review_eligible(row) is False


def test_actual_break_hidden(predictions):
    result = build_ranked_worklist(
        predictions, 2025, 1.0
    )

    assert "actual_break" not in result.columns


def test_invalid_percentile_rejected(predictions):
    predictions.loc[0, "risk_percentile"] = 1.5

    with pytest.raises(ValueError):
        build_ranked_worklist(predictions, 2025, 0.5)


def test_duplicate_rows_rejected(predictions):
    duplicate = pd.concat(
        [predictions, predictions.iloc[[0]]],
        ignore_index=True,
    )

    with pytest.raises(ValueError, match="Duplicate"):
        build_ranked_worklist(duplicate, 2025, 0.5)
