"""Evidence-based confidence and out-of-distribution flags for Contract B.

Confidence describes how much comparable training evidence exists for a
segment, not how high its risk is, so it is identical for every method in a
test year. It uses training years only.

    LOW     is_ood, or fewer than MEDIUM_SUPPORT training pipe-years share the
            segment's material x install decade
    MEDIUM  fewer than HIGH_SUPPORT such pipe-years, or the segment has data
            quality flags, a missing diameter or an ambiguous history
    HIGH    otherwise

Member 3 routes LOW/OOD rows to evidence gathering, never to renewal review.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import AGE_RANGE_TOLERANCE_YEARS, HIGH_SUPPORT, MEDIUM_SUPPORT
from .features import cohort_label, has_quality_flags, material_label, numeric


def assess_confidence(
    train: pd.DataFrame,
    test: pd.DataFrame,
    high_support: int = HIGH_SUPPORT,
    medium_support: int = MEDIUM_SUPPORT,
) -> pd.DataFrame:
    train_material = material_label(train["material"])
    test_material = material_label(test["material"])
    train_age = numeric(train["age_years"])
    test_age = numeric(test["age_years"])

    unseen_material = ~test_material.isin(set(train_material) - {"UNKNOWN"})
    age_out_of_range = (test_age < train_age.min() - AGE_RANGE_TOLERANCE_YEARS) | (
        test_age > train_age.max() + AGE_RANGE_TOLERANCE_YEARS
    )
    is_ood = unseen_material | test_age.isna() | age_out_of_range

    support_counts = (train_material + "|" + cohort_label(train["install_year"])).value_counts()
    support = (
        (test_material + "|" + cohort_label(test["install_year"]))
        .map(support_counts)
        .fillna(0)
        .astype(int)
    )

    caveats = (
        test["data_quality_flags"].map(has_quality_flags).astype(bool)
        | numeric(test["diameter_mm"]).isna()
        | test["is_ambiguous_history"].astype(bool)
    )
    label = np.select(
        [is_ood | (support < medium_support), (support < high_support) | caveats],
        ["LOW", "MEDIUM"],
        "HIGH",
    )
    return pd.DataFrame(
        {
            "is_ood": is_ood.to_numpy(dtype=bool),
            "confidence_label": label,
            "support": support.to_numpy(),
        },
        index=test.index,
    )
