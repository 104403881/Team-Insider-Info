"""Historical plans and, separately, the outcome counts used after reveal.

Ranking uses only the feature snapshot at the decision year. Breaks after
that year are counted in ``outcome_counts`` and are not passed back into
``build_worklist``.
"""

from __future__ import annotations

import pandas as pd

from jagapaip.ranking import build_worklist
from jagapaip.schema import (
    BAND_HIGH,
    FEATURE_COLUMNS,
    FORBIDDEN_FIELDS,
    PROOF_HORIZON_YEARS,
    STRATEGY_JAGAPAIP,
    STRATEGY_OLDEST,
)


def network_as_of(pipes: pd.DataFrame, breaks: pd.DataFrame | None, decision_year: int) -> pd.DataFrame:
    """Attributes and break counts knowable at the end of ``decision_year``.

    Pipes installed after that year are excluded. Breaks dated after that
    year are excluded. The result contains feature columns only.
    """
    required = {"pipe_id", "install_year", "length_m"}
    missing = required.difference(pipes.columns)
    if missing:
        raise ValueError(f"Pipe table is missing {sorted(missing)}.")

    install = pd.to_numeric(pipes["install_year"], errors="coerce")
    in_service = pipes.loc[install.notna() & (install <= decision_year)].copy()
    in_service["install_year"] = install.loc[in_service.index].astype(int)
    in_service["pipe_id"] = in_service["pipe_id"].astype(str)
    in_service["decision_year"] = int(decision_year)
    in_service["age_years"] = (int(decision_year) - in_service["install_year"]).clip(lower=0)

    if breaks is not None and not breaks.empty and "break_year" in breaks.columns:
        history = breaks.copy()
        history["pipe_id"] = history["pipe_id"].astype(str)
        history["break_year"] = pd.to_numeric(history["break_year"], errors="coerce")
        history = history.loc[history["break_year"].notna() & (history["break_year"] <= decision_year)]
        install = in_service[["pipe_id", "install_year"]]
        history = history.merge(install, on="pipe_id", how="inner")
        history = history.loc[history["break_year"] >= history["install_year"]]
        counts = history.groupby("pipe_id")["break_count"].sum()
        in_service["historical_breaks"] = in_service["pipe_id"].map(counts).fillna(0).astype(int)
    elif "historical_breaks" in in_service.columns:
        in_service["historical_breaks"] = pd.to_numeric(in_service["historical_breaks"], errors="coerce")
    else:
        in_service["historical_breaks"] = pd.NA

    for column in ("zone", "material", "diameter_mm"):
        if column not in in_service.columns:
            in_service[column] = pd.NA
    if "material" in in_service.columns:
        in_service["material"] = in_service["material"].fillna("Unknown")
    if "zone" in in_service.columns:
        in_service["zone"] = in_service["zone"].fillna("Not recorded")

    blocked = [column for column in in_service.columns if str(column).lower() in FORBIDDEN_FIELDS or str(column).lower().startswith(("future_", "outcome_", "actual_"))]
    if blocked:
        in_service = in_service.drop(columns=blocked)
    columns = list(FEATURE_COLUMNS)
    if "cost" in in_service.columns and in_service["cost"].notna().any():
        columns.append("cost")
    return in_service[columns].reset_index(drop=True)


def panel_as_of(panel: pd.DataFrame, decision_year: int) -> pd.DataFrame:
    """Feature rows for one score year. Outcome columns are dropped."""
    year = pd.to_numeric(panel["year"], errors="coerce")
    snap = panel.loc[year == int(decision_year)].copy()
    snap["pipe_id"] = snap["pipe_id"].astype(str)
    snap["decision_year"] = int(decision_year)
    if "historical_breaks" not in snap.columns and "prior_break_count" in snap.columns:
        snap["historical_breaks"] = pd.to_numeric(snap["prior_break_count"], errors="coerce")
    if "age_years" not in snap.columns and "install_year" in snap.columns:
        install = pd.to_numeric(snap["install_year"], errors="coerce")
        snap["age_years"] = (int(decision_year) - install).clip(lower=0)
    if "zone" not in snap.columns:
        snap["zone"] = "Not recorded"
    if "diameter_mm" not in snap.columns:
        snap["diameter_mm"] = pd.NA
    blocked = [column for column in snap.columns if str(column).lower() in FORBIDDEN_FIELDS or str(column).lower().startswith(("future_", "outcome_", "actual_", "target_"))]
    if blocked:
        snap = snap.drop(columns=blocked)
    columns = [column for column in FEATURE_COLUMNS if column in snap.columns]
    return snap[columns].reset_index(drop=True)


def features_for_year(dataset: dict, decision_year: int) -> pd.DataFrame:
    """Prefer the team feature panel; otherwise rebuild from pipes and the break ledger."""
    panel = dataset.get("panel")
    if panel is not None and not panel.empty and "year" in panel.columns:
        features = panel_as_of(panel, int(decision_year))
        if not features.empty:
            return attach_predictions(features, dataset.get("predictions"), int(decision_year))
    features = network_as_of(dataset["pipes"], dataset.get("breaks"), int(decision_year))
    return attach_predictions(features, dataset.get("predictions"), int(decision_year))


def attach_predictions(
    features: pd.DataFrame,
    predictions: pd.DataFrame | None,
    decision_year: int,
) -> pd.DataFrame:
    """Add supplied scores for this decision year, when a prediction file exists."""
    frame = features.copy()
    if predictions is None or predictions.empty or "predicted_risk" not in predictions.columns:
        return frame
    use = predictions.copy()
    use["pipe_id"] = use["pipe_id"].astype(str)
    if "year" in use.columns and use["year"].notna().any():
        use = use.loc[use["year"] == decision_year]
    else:
        use = use.drop(columns=[column for column in use.columns if column == "year"])
    if use.empty:
        return frame
    scores = use.groupby("pipe_id", as_index=False)["predicted_risk"].mean()
    return frame.merge(scores, on="pipe_id", how="left")


def complete_evaluation_years(
    pipes: pd.DataFrame,
    breaks: pd.DataFrame | None,
    horizon: int = PROOF_HORIZON_YEARS,
    minimum_pipes: int = 8,
) -> list[int]:
    """Years with a full outcome window still inside the break ledger."""
    if breaks is None or breaks.empty or "break_year" not in breaks.columns:
        return []
    break_years = pd.to_numeric(breaks["break_year"], errors="coerce").dropna()
    if break_years.empty:
        return []
    max_year = int(break_years.max())
    last_decision = max_year - horizon
    install = pd.to_numeric(pipes["install_year"], errors="coerce").dropna()
    if install.empty:
        return []
    first = int(install.min())
    years = []
    for year in range(max(first, last_decision - 40), last_decision + 1):
        in_service = int((install <= year).sum())
        if in_service >= minimum_pipes:
            years.append(year)
    return years


def available_evaluation_years(dataset: dict, horizon: int = PROOF_HORIZON_YEARS) -> list[int]:
    """Proof Mode years that exist in the loaded panel and have a full outcome window."""
    years = complete_evaluation_years(dataset["pipes"], dataset.get("breaks"), horizon)
    panel_years = dataset.get("meta", {}).get("panel_years") or []
    if panel_years:
        known = set(int(year) for year in panel_years)
        years = [year for year in years if year in known]
    return years


def outcome_counts(breaks: pd.DataFrame, decision_year: int, horizon: int = PROOF_HORIZON_YEARS) -> pd.DataFrame:
    """Recorded breaks strictly after the decision year, inside the horizon.

    Call this only after the user asks to reveal outcomes.
    """
    if breaks is None or breaks.empty:
        return pd.DataFrame(columns=["pipe_id", "future_breaks"])
    years = pd.to_numeric(breaks["break_year"], errors="coerce")
    window = breaks.loc[years.notna() & (years > decision_year) & (years <= decision_year + horizon)]
    if window.empty:
        return pd.DataFrame(columns=["pipe_id", "future_breaks"])
    counts = window.groupby(window["pipe_id"].astype(str))["break_count"].sum()
    return counts.rename("future_breaks").reset_index()


def build_plan(
    features: pd.DataFrame,
    budget_m: float,
    strategy: str = STRATEGY_JAGAPAIP,
) -> pd.DataFrame:
    """Rank and select from features. ``features`` must not be required to hold outcomes."""
    return build_worklist(features, budget_m=budget_m, strategy=strategy)


def plan_composition(plan: pd.DataFrame) -> dict:
    """Describe a finished plan using only scores and attributes already on it.

    These totals are not measured leak reductions, savings, or field outcomes.
    """
    selected = plan.loc[plan["selected"]] if "selected" in plan.columns else plan.iloc[0:0]
    scores = pd.to_numeric(selected["predicted_risk"], errors="coerce").fillna(0.0) if len(selected) and "predicted_risk" in selected.columns else pd.Series(dtype=float)
    lengths = pd.to_numeric(selected["length_m"], errors="coerce").fillna(0.0) if len(selected) and "length_m" in selected.columns else pd.Series(dtype=float)
    high_selected = 0
    high_network = 0
    if "risk_band" in plan.columns:
        high_network = int((plan["risk_band"] == BAND_HIGH).sum())
        if len(selected):
            high_selected = int((selected["risk_band"] == BAND_HIGH).sum())
    length_m = float(lengths.sum()) if len(lengths) else 0.0
    score_sum = float(scores.sum()) if len(scores) else 0.0
    weighted = None if length_m <= 0 else float((scores * lengths).sum() / length_m)
    return {
        "segments": int(len(selected)),
        "length_m": length_m,
        "score_sum": score_sum,
        "length_weighted_score": weighted,
        "high_risk_selected": high_selected,
        "high_risk_in_network": high_network,
    }


def compare_plans(jagapaip: pd.DataFrame, baseline: pd.DataFrame, budget_m: float) -> dict:
    """Fair plan-to-plan comparison. Both sides must use the same feature table."""
    ours_ids = set(jagapaip.loc[jagapaip["selected"], "pipe_id"].astype(str)) if len(jagapaip) else set()
    base_ids = set(baseline.loc[baseline["selected"], "pipe_id"].astype(str)) if len(baseline) else set()
    network_m = float(pd.to_numeric(jagapaip["length_m"], errors="coerce").fillna(0).sum()) if len(jagapaip) else 0.0
    return {
        "jagapaip": plan_composition(jagapaip),
        "oldest_first": plan_composition(baseline),
        "overlap_ids": sorted(ours_ids & base_ids),
        "only_jagapaip": sorted(ours_ids - base_ids),
        "only_oldest": sorted(base_ids - ours_ids),
        "budget_m": float(budget_m),
        "network_m": network_m,
        "same_selection": ours_ids == base_ids,
    }


def difference_rows(jagapaip: pd.DataFrame, baseline: pd.DataFrame, comparison: dict) -> pd.DataFrame:
    """Rows that one method funded and the other did not, with the reason each side used."""
    lookup = {}
    for plan, method in ((jagapaip, "JagaPaip"), (baseline, "Oldest-first")):
        for row in plan.to_dict(orient="records"):
            lookup.setdefault(str(row["pipe_id"]), row)["shown_in"] = method
    rows = []
    for pipe_id in comparison["only_jagapaip"]:
        row = lookup[pipe_id]
        rows.append(_difference_row(row, "JagaPaip only", "Higher risk score under the length budget"))
    for pipe_id in comparison["only_oldest"]:
        row = lookup[pipe_id]
        rows.append(_difference_row(row, "Oldest-first only", "Older install year under the same length budget"))
    return pd.DataFrame(rows)


def _difference_row(row: dict, chosen_by: str, why: str) -> dict:
    return {
        "Pipe ID": str(row["pipe_id"]),
        "Chosen by": chosen_by,
        "Why": why,
        "Risk score": row.get("predicted_risk"),
        "Risk band": row.get("risk_band"),
        "Recommended action": row.get("recommended_action"),
        "Age (years)": row.get("age_years"),
        "Installed": row.get("install_year"),
        "Length (m)": row.get("length_m"),
        "Location": row.get("zone"),
    }


def capture_summary(plan: pd.DataFrame, outcomes: pd.DataFrame | None) -> dict:
    """Count recorded outcome-window events for a plan that was already chosen.

    This does not rebuild the plan. For an event ledger, a selected pipe with
    no outcome row has zero recorded events. That is not an accuracy score.
    """
    selected = plan.loc[plan["selected"], ["pipe_id", "length_m"]].copy()
    selected["pipe_id"] = selected["pipe_id"].astype(str)
    length_m = float(selected["length_m"].sum()) if len(selected) else 0.0
    if outcomes is None:
        return {
            "segments_selected": int(len(selected)),
            "length_m": length_m,
            "captured_breaks": None,
            "segments_with_a_break": None,
            "breaks_per_km": None,
            "comparable": False,
        }
    merged = selected.merge(outcomes, on="pipe_id", how="left")
    if "future_breaks" not in merged.columns:
        counts = pd.Series(0, index=merged.index, dtype=float)
    else:
        counts = merged["future_breaks"].fillna(0)
    captured = int(counts.sum())
    per_km = None if length_m <= 0 else captured / (length_m / 1000.0)
    return {
        "segments_selected": int(len(selected)),
        "length_m": length_m,
        "captured_breaks": captured,
        "segments_with_a_break": int((counts > 0).sum()),
        "breaks_per_km": per_km,
        "comparable": True,
    }
