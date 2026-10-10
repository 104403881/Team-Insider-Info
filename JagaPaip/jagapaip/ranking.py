"""Score pipes and spend a network-length budget.

This module never reads break dates or future outcomes. Callers pass a
feature table. Length is used only when deciding whether a segment fits
the remaining budget.
"""

from __future__ import annotations

import math

import pandas as pd

from jagapaip.schema import (
    ACTION_INSPECT,
    ACTION_MONITOR,
    ACTION_RENEWAL,
    AGE_CAP_YEARS,
    AGE_WEIGHT,
    BAND_HIGH,
    BAND_LOW,
    BAND_MODERATE,
    BREAK_CAP,
    BREAK_WEIGHT,
    FORBIDDEN_FIELDS,
    INSPECT_THRESHOLD,
    MATERIAL_CODE_MAP,
    MATERIAL_WEIGHTS,
    RENEWAL_THRESHOLD,
    STRATEGY_JAGAPAIP,
    STRATEGY_OLDEST,
)

SCORE_SOURCE_HEURISTIC = "screening_heuristic"
SCORE_SOURCE_SUPPLIED = "supplied_prediction"


class RankingError(ValueError):
    """The feature table cannot be ranked."""


def drop_forbidden(frame: pd.DataFrame) -> pd.DataFrame:
    """Remove outcome columns so they cannot affect sort order."""
    blocked = [column for column in frame.columns if _is_forbidden(column)]
    if not blocked:
        return frame.copy()
    return frame.drop(columns=blocked)


def _is_forbidden(column: str) -> bool:
    name = str(column).strip().lower()
    return name in FORBIDDEN_FIELDS or name.startswith(("future_", "outcome_", "actual_", "target_"))


def action_for_score(score: float) -> str:
    if score >= RENEWAL_THRESHOLD:
        return ACTION_RENEWAL
    if score >= INSPECT_THRESHOLD:
        return ACTION_INSPECT
    return ACTION_MONITOR


def band_for_score(score: float) -> str:
    if score >= RENEWAL_THRESHOLD:
        return BAND_HIGH
    if score >= INSPECT_THRESHOLD:
        return BAND_MODERATE
    return BAND_LOW


def _material_weight(material: object) -> tuple[float, str]:
    if material is None or (isinstance(material, float) and math.isnan(material)):
        return MATERIAL_WEIGHTS["Unknown"], "Unknown"
    key = str(material).strip()
    mapped = MATERIAL_CODE_MAP.get(key) or MATERIAL_CODE_MAP.get(key.upper())
    if mapped:
        key = mapped
    if key in MATERIAL_WEIGHTS:
        return MATERIAL_WEIGHTS[key], key
    folded = {name.lower(): name for name in MATERIAL_WEIGHTS}
    match = folded.get(key.lower())
    if match:
        return MATERIAL_WEIGHTS[match], match
    return MATERIAL_WEIGHTS["Unknown"], "Unknown"


def heuristic_components(age_years: float, material: object, historical_breaks: float) -> dict[str, float | str]:
    """Transparent screening score from age, material, and recorded breaks."""
    age = 0.0 if pd.isna(age_years) else max(float(age_years), 0.0)
    breaks = 0.0 if pd.isna(historical_breaks) else max(float(historical_breaks), 0.0)
    age_component = AGE_WEIGHT * min(age, AGE_CAP_YEARS) / AGE_CAP_YEARS
    material_component, material_name = _material_weight(material)
    break_component = BREAK_WEIGHT * min(breaks, BREAK_CAP) / BREAK_CAP
    score = min(1.0, age_component + material_component + break_component)
    return {
        "predicted_risk": score,
        "age_component": age_component,
        "material_component": material_component,
        "break_component": break_component,
        "material_used": material_name,
    }


def _explanation_heuristic(row: pd.Series) -> str:
    year = int(row["decision_year"]) if "decision_year" in row.index and pd.notna(row.get("decision_year")) else None
    year_text = f" at decision year {year}" if year is not None else ""
    age_value = row["age_years"] if "age_years" in row.index else pd.NA
    break_value = row["historical_breaks"] if "historical_breaks" in row.index else pd.NA
    age = "not recorded" if pd.isna(age_value) else str(int(round(float(age_value))))
    if pd.isna(break_value):
        break_text = "break history was not in the source, so that term contributed 0"
    else:
        breaks = int(break_value)
        break_text = f"recorded breaks {row['break_component']:.2f} ({breaks} on or before the decision year)"
    unknown = ""
    if str(row["material_used"]) == "Unknown":
        unknown = " Unknown material uses the published neutral weight, not an inspected material. "
    return (
        f"Screening score {row['predicted_risk']:.2f}{year_text}. "
        f"Contributions: installation age {row['age_component']:.2f} ({age} years), "
        f"material {row['material_component']:.2f} ({row['material_used']}), "
        f"{break_text}. "
        f"{unknown}"
        "Length is used only for the budget, not for the score. "
        "These contributions order the queue. They are not a finding that any factor caused a break."
    )


def _explanation_supplied(row: pd.Series) -> str:
    year = int(row["decision_year"]) if "decision_year" in row and pd.notna(row["decision_year"]) else None
    year_text = f" for decision year {year}" if year is not None else ""
    return (
        f"Score {row['predicted_risk']:.2f} was supplied by fold predictions{year_text}. "
        "JagaPaip did not recompute it, and the score does not by itself show why a failure would occur. "
        "It is not a finding that any factor caused a break. "
        f"Recommended action uses fixed bands: {ACTION_RENEWAL} at or above {RENEWAL_THRESHOLD:.2f}, "
        f"{ACTION_INSPECT} at or above {INSPECT_THRESHOLD:.2f}, otherwise {ACTION_MONITOR}."
    )


def score_segments(features: pd.DataFrame) -> pd.DataFrame:
    """Add a risk score, band, action, and plain-language explanation.

    A supplied ``predicted_risk`` column is kept. Missing scores fall back
    to the screening heuristic. Forbidden outcome columns are dropped first.
    """
    frame = drop_forbidden(features)
    if "pipe_id" not in frame.columns or "length_m" not in frame.columns:
        raise RankingError("Scoring requires pipe_id and length_m.")
    if frame.empty:
        scored = frame.copy()
        for column in (
            "predicted_risk",
            "age_component",
            "material_component",
            "break_component",
            "material_used",
            "score_source",
            "risk_band",
            "recommended_action",
            "explanation",
        ):
            if column not in scored.columns:
                scored[column] = pd.Series(dtype="object")
        return scored

    supplied = "predicted_risk" in frame.columns
    rows: list[dict] = []
    for item in frame.to_dict(orient="records"):
        has_supplied = supplied and pd.notna(item.get("predicted_risk"))
        if has_supplied:
            components = {
                "predicted_risk": float(item["predicted_risk"]),
                "age_component": math.nan,
                "material_component": math.nan,
                "break_component": math.nan,
                "material_used": item.get("material", "Unknown"),
                "score_source": SCORE_SOURCE_SUPPLIED,
            }
        else:
            components = heuristic_components(
                item.get("age_years", 0),
                item.get("material", "Unknown"),
                item.get("historical_breaks", 0),
            )
            components["score_source"] = SCORE_SOURCE_HEURISTIC
        item.update(components)
        rows.append(item)

    scored = pd.DataFrame(rows)
    if scored.empty:
        scored["risk_band"] = []
        scored["recommended_action"] = []
        scored["explanation"] = []
        return scored

    scored["risk_band"] = scored["predicted_risk"].map(band_for_score)
    scored["recommended_action"] = scored["predicted_risk"].map(action_for_score)
    scored["explanation"] = scored.apply(
        lambda row: _explanation_supplied(row) if row["score_source"] == SCORE_SOURCE_SUPPLIED else _explanation_heuristic(row),
        axis=1,
    )
    return scored


def _order(scored: pd.DataFrame, strategy: str) -> pd.DataFrame:
    frame = scored.copy()
    if "historical_breaks" not in frame.columns:
        frame["historical_breaks"] = 0
    if "age_years" not in frame.columns:
        frame["age_years"] = 0
    if "install_year" not in frame.columns:
        frame["install_year"] = pd.NA
    if strategy == STRATEGY_JAGAPAIP:
        return frame.sort_values(
            by=["predicted_risk", "historical_breaks", "age_years", "pipe_id"],
            ascending=[False, False, False, True],
            kind="mergesort",
        )
    if strategy == STRATEGY_OLDEST:
        return frame.sort_values(
            by=["install_year", "pipe_id"],
            ascending=[True, True],
            kind="mergesort",
            na_position="last",
        )
    raise RankingError(f"Unknown strategy: {strategy}")


def apply_length_budget(
    ordered: pd.DataFrame,
    budget_m: float,
    size_column: str = "length_m",
) -> pd.DataFrame:
    """Select segments in the given order until the budget is spent.

    A segment larger than the remainder is skipped, so a later smaller segment
    can still be selected. The default size is length in metres. A supplied
    cost column can be used instead. Costs are never invented.
    """
    if budget_m < 0:
        raise RankingError("budget_m must be zero or greater.")
    if "length_m" not in ordered.columns:
        raise RankingError("Budget selection requires length_m.")
    if size_column not in ordered.columns:
        raise RankingError(f"Budget selection requires {size_column}.")

    if size_column == "length_m":
        missing_text = "Not selected - length is missing or not positive"
        fitted_text = "Selected within the remaining length budget"
        used_text = "Not selected - length budget already used"
        overflow_text = "Not selected - longer than the remaining length budget"
    else:
        missing_text = "Not selected - cost is missing or not positive"
        fitted_text = "Selected within the remaining cost budget"
        used_text = "Not selected - cost budget already used"
        overflow_text = "Not selected - larger than the remaining cost budget"

    remaining = float(budget_m)
    selected: list[bool] = []
    reasons: list[str] = []
    cumulative_length: list[float] = []
    cumulative_budget: list[float] = []
    spent_length = 0.0
    spent_budget = 0.0

    for _, row in ordered.iterrows():
        length = row["length_m"]
        size = row[size_column]
        length_missing = pd.isna(length) or float(length) <= 0
        size_missing = pd.isna(size) or float(size) <= 0
        if length_missing or (size_column != "length_m" and size_missing):
            selected.append(False)
            reasons.append(missing_text)
            cumulative_length.append(spent_length)
            cumulative_budget.append(spent_budget)
            continue
        length_value = float(length)
        size_value = length_value if size_column == "length_m" else float(size)
        if size_value <= remaining + 1e-9:
            selected.append(True)
            reasons.append(fitted_text)
            spent_length += length_value
            spent_budget += size_value
            remaining -= size_value
        elif remaining <= 1e-6:
            selected.append(False)
            reasons.append(used_text)
        else:
            selected.append(False)
            reasons.append(overflow_text)
        cumulative_length.append(spent_length)
        cumulative_budget.append(spent_budget)

    result = ordered.copy()
    result["selected"] = selected
    result["selection_reason"] = reasons
    result["cumulative_selected_m"] = cumulative_length
    result["cumulative_budget_units"] = cumulative_budget
    result["rank"] = range(1, len(result) + 1)
    column_order = [
        "rank",
        "selected",
        "selection_reason",
        "cumulative_selected_m",
        "cumulative_budget_units",
    ]
    front = [column for column in column_order if column in result.columns]
    rest = [column for column in result.columns if column not in front]
    return result[front + rest].reset_index(drop=True)


def build_worklist(
    features: pd.DataFrame,
    budget_m: float,
    strategy: str = STRATEGY_JAGAPAIP,
    size_column: str = "length_m",
) -> pd.DataFrame:
    """Score, rank, and select. Outcome columns in ``features`` are ignored."""
    scored = score_segments(features)
    ordered = _order(scored, strategy)
    return apply_length_budget(ordered, budget_m, size_column=size_column)


def plan_summary(plan: pd.DataFrame, budget_m: float) -> dict:
    """Totals for the cards above a worklist."""
    if plan.empty:
        return {
            "candidates": 0,
            "selected_segments": 0,
            "selected_m": 0.0,
            "budget_m": float(budget_m),
            "unspent_m": float(budget_m),
            "network_m": 0.0,
            "high_risk_segments": 0,
            "high_risk_in_plan": 0,
            "actions": {},
            "marginal_pipe_id": None,
        }
    selected = plan.loc[plan["selected"]]
    selected_m = float(selected["length_m"].sum()) if len(selected) else 0.0
    marginal = None
    if len(selected):
        marginal = str(selected.sort_values("rank").iloc[-1]["pipe_id"])
    actions = selected["recommended_action"].value_counts().to_dict() if len(selected) else {}
    return {
        "candidates": int(len(plan)),
        "selected_segments": int(len(selected)),
        "selected_m": selected_m,
        "budget_m": float(budget_m),
        "unspent_m": max(0.0, float(budget_m) - selected_m),
        "network_m": float(plan["length_m"].sum()),
        "high_risk_segments": int((plan["risk_band"] == BAND_HIGH).sum()),
        "high_risk_in_plan": int(((plan["risk_band"] == BAND_HIGH) & plan["selected"]).sum()),
        "actions": {str(key): int(value) for key, value in actions.items()},
        "marginal_pipe_id": marginal,
    }
