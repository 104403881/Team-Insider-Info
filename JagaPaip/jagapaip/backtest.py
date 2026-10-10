"""Historical evaluation of plans that were fixed before outcomes were read.

Plans are always built from a feature snapshot first. Outcome counts are read
afterwards and joined only to the already-selected segments. A feature table
that carries outcome columns is rejected rather than silently cleaned.
"""

from __future__ import annotations

import pandas as pd

from jagapaip.proof import build_plan, outcome_counts
from jagapaip.ranking import _is_forbidden
from jagapaip.schema import PROOF_HORIZON_YEARS, STRATEGY_JAGAPAIP, STRATEGY_OLDEST

CAPTURE_FRACTION = 0.05
STRATEGIES = (STRATEGY_JAGAPAIP, STRATEGY_OLDEST)


class LeakageError(ValueError):
    """A feature table passed to the backtest contains outcome columns."""


def assert_features_only(features: pd.DataFrame) -> None:
    leaked = [column for column in features.columns if _is_forbidden(column)]
    if leaked:
        raise LeakageError(f"Feature table contains outcome columns: {leaked}")


def eligible_population(features: pd.DataFrame) -> pd.DataFrame:
    """In-service segments at the decision year with a usable length."""
    length = pd.to_numeric(features["length_m"], errors="coerce")
    return features.loc[length.notna() & (length > 0)].copy()


def window_outcomes(breaks: pd.DataFrame | None, eligible_ids: set[str], year: int, horizon: int) -> dict:
    """Split outcome-window breaks into eligible and excluded segments."""
    counts = outcome_counts(breaks, year, horizon) if breaks is not None else pd.DataFrame(columns=["pipe_id", "future_breaks"])
    counts["pipe_id"] = counts["pipe_id"].astype(str)
    inside = counts.loc[counts["pipe_id"].isin(eligible_ids)]
    outside = counts.loc[~counts["pipe_id"].isin(eligible_ids)]
    return {
        "per_pipe": inside.reset_index(drop=True),
        "eligible_breaks": int(inside["future_breaks"].sum()) if len(inside) else 0,
        "excluded_breaks": int(outside["future_breaks"].sum()) if len(outside) else 0,
        "segments_with_break": int((inside["future_breaks"] > 0).sum()) if len(inside) else 0,
    }


def score_plan(plan: pd.DataFrame, per_pipe: pd.DataFrame, eligible_breaks: int) -> dict:
    selected = plan.loc[plan["selected"], ["pipe_id", "length_m"]].copy()
    selected["pipe_id"] = selected["pipe_id"].astype(str)
    merged = selected.merge(per_pipe, on="pipe_id", how="left")
    hits = merged["future_breaks"].fillna(0) if "future_breaks" in merged.columns else pd.Series(0, index=merged.index)
    captured = int(hits.sum())
    length_m = float(selected["length_m"].sum()) if len(selected) else 0.0
    return {
        "segments": int(len(selected)),
        "length_m": length_m,
        "captured_breaks": captured,
        "segments_hit": int((hits > 0).sum()),
        "capture_rate": None if eligible_breaks <= 0 else captured / eligible_breaks,
        "breaks_per_km": None if length_m <= 0 else captured / (length_m / 1000),
    }


def run_backtest(
    features: pd.DataFrame,
    breaks: pd.DataFrame | None,
    year: int,
    budget_m: float,
    horizon: int = PROOF_HORIZON_YEARS,
    capture_fraction: float = CAPTURE_FRACTION,
) -> dict:
    """Build both plans from features, then score them against the outcome window.

    Every plan is built before ``breaks`` is read. Capture@fraction uses a
    separate budget equal to ``capture_fraction`` of eligible network length.
    """
    assert_features_only(features)
    eligible = eligible_population(features)
    network_m = float(eligible["length_m"].sum())
    capture_budget_m = network_m * capture_fraction

    plans = {
        "budget": {strategy: build_plan(eligible, budget_m, strategy) for strategy in STRATEGIES},
        "capture": {strategy: build_plan(eligible, capture_budget_m, strategy) for strategy in STRATEGIES},
    }

    window = window_outcomes(breaks, set(eligible["pipe_id"].astype(str)), int(year), int(horizon))
    results = {
        group: {strategy: score_plan(plan, window["per_pipe"], window["eligible_breaks"]) for strategy, plan in group_plans.items()}
        for group, group_plans in plans.items()
    }

    def lift(group: str) -> float | None:
        ours = results[group][STRATEGY_JAGAPAIP]["capture_rate"]
        base = results[group][STRATEGY_OLDEST]["capture_rate"]
        if ours is None or base is None or base == 0:
            return None
        return ours / base

    return {
        "year": int(year),
        "horizon": int(horizon),
        "window": (int(year) + 1, int(year) + int(horizon)),
        "eligible_segments": int(len(eligible)),
        "eligible_length_m": network_m,
        "eligible_breaks": window["eligible_breaks"],
        "excluded_breaks": window["excluded_breaks"],
        "segments_with_break": window["segments_with_break"],
        "budget_m": float(budget_m),
        "capture_fraction": float(capture_fraction),
        "capture_budget_m": capture_budget_m,
        "at_budget": results["budget"],
        "at_capture": results["capture"],
        "lift_at_budget": lift("budget"),
        "lift_at_capture": lift("capture"),
        "plans": plans,
    }
