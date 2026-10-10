
"""JagaPaip - Member 3: Decision & Explainability."""

import math
from numbers import Integral

import pandas as pd

REQUIRED_COLUMNS = {
    "segment_id",
    "test_year",
    "method",
    "model_score",
    "risk_percentile",
    "confidence_label",
    "is_ood",
    "actual_break",
    "length_m",
}

VALID_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}


def validate_contract_b(df: pd.DataFrame) -> None:
    """Validate Contract B before making decisions."""

    missing = REQUIRED_COLUMNS - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing Contract B columns: {sorted(missing)}"
        )

    if df.empty:
        raise ValueError("Contract B input is empty.")

    key_columns = ["segment_id", "test_year", "method"]

    if df[key_columns].isna().any().any():
        raise ValueError("Contract B identifiers cannot be missing.")

    if df.duplicated(key_columns).any():
        raise ValueError(
            "Duplicate segment_id × test_year × method rows."
        )

    if df["segment_id"].astype(str).str.strip().eq("").any():
        raise ValueError("segment_id cannot be blank.")

    confidence = df["confidence_label"].astype(str).str.upper()

    if not confidence.isin(VALID_CONFIDENCE).all():
        raise ValueError("Invalid confidence_label.")

    if df["is_ood"].isna().any():
        raise ValueError("is_ood cannot be missing.")

    if not df["is_ood"].isin([True, False]).all():
        raise ValueError("is_ood must be boolean.")

    for column in [
        "test_year",
        "model_score",
        "risk_percentile",
        "length_m",
    ]:
        values = pd.to_numeric(df[column], errors="coerce")

        if values.isna().any():
            raise ValueError(f"{column} must be numeric.")

        if not values.map(math.isfinite).all():
            raise ValueError(f"{column} must be finite.")

    if not df["risk_percentile"].between(0, 1).all():
        raise ValueError("risk_percentile must be between 0 and 1.")

    if (df["length_m"] <= 0).any():
        raise ValueError("length_m must be positive.")

    if not df["actual_break"].isin([0, 1]).all():
        raise ValueError("actual_break must contain only 0 or 1.")


def renewal_review_eligible(row: pd.Series) -> bool:
    """
    LOW confidence or OOD segments must never automatically
    receive RENEWAL_REVIEW.
    """

    confidence = str(row["confidence_label"]).upper()
    is_ood = bool(row["is_ood"])

    return confidence != "LOW" and not is_ood


def build_ranked_worklist(
    predictions: pd.DataFrame,
    test_year: int,
    budget_fraction: float,
) -> pd.DataFrame:
    """
    Generate the champion worklist for one test year.

    Ranking:
      1. risk_percentile descending
      2. segment_id ascending

    Budget:
      budget_fraction * total champion length for that year.

    Select the longest prefix within budget.
    Stop at the first overflow; never skip ahead.
    """

    validate_contract_b(predictions)

    if isinstance(test_year, bool) or not isinstance(test_year, Integral):
        raise ValueError("test_year must be an integer.")

    test_year = int(test_year)

    if (
        not math.isfinite(float(budget_fraction))
        or not 0 <= budget_fraction <= 1
    ):
        raise ValueError("budget_fraction must be between 0 and 1.")

    year_rows = predictions[
        predictions["test_year"] == test_year
    ].copy()

    if year_rows.empty:
        raise ValueError(f"No rows for test_year={test_year}.")

    # Main worklist uses champion only.
    champion = year_rows[
        year_rows["method"] == "champion"
    ].copy()

    if champion.empty:
        raise ValueError("No champion predictions for this year.")

    champion["confidence_label"] = (
        champion["confidence_label"].astype(str).str.upper()
    )

    # Exact frozen sorting contract.
    champion = champion.sort_values(
        ["risk_percentile", "segment_id"],
        ascending=[False, True],
        kind="stable",
    ).reset_index(drop=True)

    # Budget denominator: champion rows only.
    # Confirm this interpretation with Member 2.
    total_length = float(champion["length_m"].sum())
    budget_length = budget_fraction * total_length

    champion["rank"] = range(1, len(champion) + 1)

    champion["cumulative_length_m"] = (
        champion["length_m"].cumsum()
    )

    champion["budget_fraction"] = budget_fraction
    champion["total_length_m"] = total_length
    champion["budget_length_m"] = budget_length

    # Prefix selection: do not skip segments after an overflow.
    champion["selected"] = (
        champion["cumulative_length_m"] <= budget_length
    )

    # Confidence safeguard.
    champion["renewal_review_eligible"] = champion.apply(
        renewal_review_eligible,
        axis=1,
    )

    champion["selection_reason"] = champion["selected"].map({
        True: "Selected: within ranked budget prefix",
        False: "Not selected: outside budget prefix",
    })

    champion["confidence_note"] = champion.apply(
        lambda row: (
            "Manual assessment required: LOW confidence"
            if row["confidence_label"] == "LOW"
            else "Manual assessment required: OOD"
            if row["is_ood"]
            else "Eligible for agreed action rules"
        ),
        axis=1,
    )

# Keep actual_break for internal evaluation and Proof Mode.
# The normal UI must hide this column until the reveal.
    return champion
