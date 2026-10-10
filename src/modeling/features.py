"""Small helpers shared by the rankers and the confidence rules."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd


def numeric(series: pd.Series) -> pd.Series:
    """Coerce to float64 with NaN for missing values (handles nullable dtypes)."""
    return pd.to_numeric(series, errors="coerce").astype("float64")


def material_label(material: pd.Series) -> pd.Series:
    return material.fillna("UNKNOWN").astype(str)


def cohort_label(install_year: pd.Series) -> pd.Series:
    """Installation decade such as '1950s'; missing years become 'UNKNOWN'."""
    decade = np.floor(numeric(install_year) / 10) * 10
    labels = decade.fillna(0).astype(int).astype(str) + "s"
    return labels.where(decade.notna(), "UNKNOWN")


def has_quality_flags(value) -> bool:
    """True when a data_quality_flags cell (a JSON array as text) lists any flag."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if text in ("", "[]"):
        return False
    try:
        return bool(json.loads(text))
    except ValueError:
        return True
