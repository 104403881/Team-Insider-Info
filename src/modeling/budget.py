"""Equal network-length selection and the metrics computed on it.

Every method in a test year is judged on the same eligible segments, so the
budget (a fraction of their total length) is identical for every method.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


def canonical_order(df: pd.DataFrame, score_col: str = "risk_percentile") -> pd.DataFrame:
    """Deterministic ranking order shared with Contract C: score desc, segment_id asc."""
    return df.sort_values([score_col, "segment_id"], ascending=[False, True])


def select_within_budget(lengths_in_order, budget_length: float) -> np.ndarray:
    """Mask for the longest prefix whose cumulative length does not exceed the budget.

    Selection stops at the first segment that would overflow rather than
    skipping it. The selected set is therefore always a prefix of the ranking,
    and the UI can reproduce it by filtering on cumulative length.
    """
    return np.cumsum(np.asarray(lengths_in_order, dtype=float)) <= budget_length


@dataclass(frozen=True)
class BudgetOutcome:
    budget: float
    network_length_m: float
    budget_length_m: float
    selected_segments: int
    selected_length_m: float
    breaks_captured: int
    total_breaks: int
    capture: float | None
    precision: float | None
    observed_non_events: int


def evaluate_budget(
    group: pd.DataFrame, budget: float, score_col: str = "risk_percentile"
) -> BudgetOutcome:
    """Evaluate one (test_year, method) ranking at one network-length budget.

    ``group`` holds every eligible segment for that year with segment_id,
    length_m, actual_break and the score column.
    """
    ordered = canonical_order(group, score_col)
    lengths = ordered["length_m"].to_numpy(dtype=float)
    actual = ordered["actual_break"].to_numpy(dtype=int)
    # fsum is exact, so the budget is bit-identical however a method orders rows.
    network_length = math.fsum(lengths)
    budget_length = budget * network_length
    selected = select_within_budget(lengths, budget_length)
    n_selected = int(selected.sum())
    captured = int(actual[selected].sum())
    total = int(actual.sum())
    return BudgetOutcome(
        budget=budget,
        network_length_m=network_length,
        budget_length_m=budget_length,
        selected_segments=n_selected,
        selected_length_m=float(np.cumsum(lengths)[n_selected - 1]) if n_selected else 0.0,
        breaks_captured=captured,
        total_breaks=total,
        capture=captured / total if total else None,
        precision=captured / n_selected if n_selected else None,
        observed_non_events=n_selected - captured,
    )


def capture_at_budget(
    group: pd.DataFrame, budget: float, score_col: str = "risk_percentile"
) -> float | None:
    """Share of the year's broken segments that fall inside the length budget."""
    return evaluate_budget(group, budget, score_col).capture


def precision_at_budget(
    group: pd.DataFrame, budget: float, score_col: str = "risk_percentile"
) -> float | None:
    """Share of selected segments that had a recorded break that year."""
    return evaluate_budget(group, budget, score_col).precision
