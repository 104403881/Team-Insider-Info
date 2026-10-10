"""Paired segment bootstrap for capture-at-budget uncertainty.

Within each test year, segments are resampled with replacement and every
method's ranking is re-judged with the same equal-length selection rule.
All methods share each resample, so differences between methods are paired.
Years are resampled independently; a pooled replicate averages that
replicate's yearly captures, mirroring how capture_at_XX is averaged.

A resample is represented by multinomial counts (how many times each segment
was drawn). Copies of a segment sit together in the ranking, so the
cumulative-length prefix rule applies to the weighted segments directly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import BOOTSTRAP_RESAMPLES, BUDGETS, CONFIDENCE_LEVEL, SEED, budget_label
from .summaries import nanmean_rows, round_or_none

CHUNK = 100  # resamples per batch; bounds memory at CHUNK x segments


def weighted_capture(weights: np.ndarray, lengths: np.ndarray, actual: np.ndarray, budgets) -> np.ndarray:
    """Capture for each weight row and budget; arrays are in ranking order.

    weights: (resamples, segments). Returns (resamples, budgets), NaN where the
    resample contains no broken segment.
    """
    cumulative = np.cumsum(weights * lengths, axis=1)
    breaks = weights * actual
    total_breaks = breaks.sum(axis=1)
    out = np.empty((weights.shape[0], len(budgets)))
    for k, budget in enumerate(budgets):
        selected = cumulative <= budget * cumulative[:, -1:]
        captured = (breaks * selected).sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[:, k] = np.where(total_breaks > 0, captured / total_breaks, np.nan)
    return out


def bootstrap_year(
    year_predictions: pd.DataFrame, budgets, n_resamples: int, seed: int, year: int
) -> dict[str, np.ndarray]:
    """Capture replicates for one test year: {method: array (n_resamples, n_budgets)}."""
    segments = np.sort(year_predictions["segment_id"].unique())
    n = len(segments)
    position = pd.Series(np.arange(n), index=segments)
    rankings = {}
    for method, group in year_predictions.groupby("method", sort=True):
        ordered = group.sort_values(["risk_percentile", "segment_id"], ascending=[False, True])
        rankings[method] = (
            position[ordered["segment_id"].to_numpy()].to_numpy(),
            ordered["length_m"].to_numpy(dtype=float),
            ordered["actual_break"].to_numpy(dtype=float),
        )

    rng = np.random.default_rng([seed, int(year)])
    replicates = {method: np.empty((n_resamples, len(budgets))) for method in rankings}
    for start in range(0, n_resamples, CHUNK):
        size = min(CHUNK, n_resamples - start)
        # One draw per segment position, shared by every method (paired).
        counts = rng.multinomial(n, np.full(n, 1.0 / n), size=size)
        for method, (order, lengths, actual) in rankings.items():
            replicates[method][start : start + size] = weighted_capture(counts[:, order], lengths, actual, budgets)
    return replicates


def bootstrap_uncertainty(
    predictions: pd.DataFrame,
    champion: str,
    *,
    budgets=BUDGETS,
    n_resamples: int = BOOTSTRAP_RESAMPLES,
    confidence: float = CONFIDENCE_LEVEL,
    seed: int = SEED,
) -> dict:
    per_year = {
        int(year): bootstrap_year(group, budgets, n_resamples, seed, year)
        for year, group in predictions.groupby("test_year", sort=True)
    }
    methods = sorted(next(iter(per_year.values())))
    tail = (1 - confidence) / 2 * 100

    def interval(values: np.ndarray):
        values = values[~np.isnan(values)]
        if not len(values):
            return None
        low, high = np.percentile(values, [tail, 100 - tail])
        return [round_or_none(low), round_or_none(high)]

    capture, difference = {}, {}
    for k, budget in enumerate(budgets):
        capture_block, difference_block = {}, {}
        for method in methods:
            yearly = {year: reps[method][:, k] for year, reps in per_year.items()}
            capture_block[method] = {
                "ci_mean": interval(nanmean_rows(np.column_stack(list(yearly.values())))),
                "by_year": {str(year): interval(values) for year, values in yearly.items()},
            }
            if method == "oldest" or "oldest" not in methods:
                continue
            yearly_diff = {year: reps[method][:, k] - reps["oldest"][:, k] for year, reps in per_year.items()}
            pooled = nanmean_rows(np.column_stack(list(yearly_diff.values())))
            valid = pooled[~np.isnan(pooled)]
            difference_block[method] = {
                "ci_mean": interval(pooled),
                "share_of_resamples_above_zero": round_or_none((valid > 0).mean(), 4) if len(valid) else None,
                "by_year": {str(year): interval(values) for year, values in yearly_diff.items()},
            }
        capture_block["champion"] = capture_block[champion]
        if champion in difference_block:
            difference_block["champion"] = difference_block[champion]
        capture[budget_label(budget)] = capture_block
        difference[budget_label(budget)] = difference_block

    return {
        "method": "paired segment bootstrap within each test year; pooled replicates average the yearly replicates",
        "n_resamples": n_resamples,
        "confidence_level": confidence,
        "seed": seed,
        "capture": capture,
        "difference_vs_oldest": difference,
    }
