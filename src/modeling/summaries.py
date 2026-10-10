"""Number helpers for metrics.json: strict-JSON-safe rounding and means."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def round_or_none(value, digits: int = 6):
    """Round to ``digits``; None and NaN become None so json.dumps(allow_nan=False) works."""
    if value is None:
        return None
    value = float(value)
    return None if math.isnan(value) else round(value, digits)


def mean_or_none(values) -> float | None:
    """Mean of the non-missing values, or None when there are none."""
    s = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    return float(s.mean()) if len(s) else None


def nanmean_rows(matrix: np.ndarray) -> np.ndarray:
    """Row means ignoring NaN; all-NaN rows give NaN without a warning."""
    valid = ~np.isnan(matrix)
    counts = valid.sum(axis=1)
    sums = np.where(valid, matrix, 0.0).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(counts > 0, sums / counts, np.nan)
