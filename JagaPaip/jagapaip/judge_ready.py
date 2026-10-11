
"""Judge-facing, read-only summaries of existing, measured JagaPaip results.

Nothing in this module scores pipes, refits models, alters the frozen budget
rule, or promotes an observed non-event into a proven false alarm.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import pandas as pd

SIMPLE_METHODS = ("oldest", "prior_breaks", "lookup", "logistic")


def _number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def risk_pattern(row: Mapping) -> str:
    """Descriptive record pattern, never a physical failure diagnosis."""
    count = _number(row.get("historical_breaks"))
    if count is None:
        return "Break history unavailable"
    if count >= 2:
        return "Repeat-break history"
    if count >= 1:
        return "Prior recorded break"
    age = _number(row.get("age_years"))
    if age is not None and age >= 50:
        return "Older segment; no recorded break"
    return "No recorded prior break"


def evidence_coverage(row: Mapping) -> tuple[str, str]:
    """Assess completeness of visible evidence, not model confidence."""
    missing: list[str] = []

    for column, title in (
        ("age_years", "age"),
        ("diameter_mm", "diameter"),
        ("historical_breaks", "prior breaks"),
    ):
        if _number(row.get(column)) is None:
            missing.append(title)

    material = str(row.get("material", "")).strip().lower()
    if material in ("", "none", "nan", "unknown", "not recorded", "<na>"):
        missing.append("material")

    if not missing:
        return (
            "Complete core fields",
            "Age, diameter, material and prior-break count are present.",
        )

    return (
        "Incomplete core fields",
        "Missing or unknown: " + ", ".join(missing) + ".",
    )


def evaluation_brief(metrics: dict, budget: float = 0.05) -> dict | None:
    """Read reported evaluation metrics without recalculating accuracy."""
    if not metrics or metrics.get("is_synthetic") is True:
        return None

    key = f"{round(budget * 100):02d}"
    champion = metrics.get("methods", {}).get("champion", {})
    oldest = metrics.get("methods", {}).get("oldest", {})

    required = [
        champion.get(f"capture_at_{key}"),
        oldest.get(f"capture_at_{key}"),
        champion.get(f"precision_at_{key}"),
        champion.get(f"observed_non_events_at_{key}"),
    ]

    if any(_number(value) is None for value in required):
        return None

    return {
        "budget": budget,
        "capture": float(required[0]),
        "oldest_capture": float(required[1]),
        "precision": float(required[2]),
        "observed_non_events": int(required[3]),
        "champion_method": metrics.get("champion_method", "not identified"),
        "test_years": metrics.get("test_years", []),
    }


def time_separated_selection(metrics: dict, budget: float = 0.05) -> dict | None:
    """Retrospective earlier-year selection and final-year comparison.

    This is NOT a fresh untouched holdout: the original champion was
    already selected using all test years.
    """
    if not metrics or metrics.get("is_synthetic") is True:
        return None

    years = sorted({int(y) for y in metrics.get("test_years", [])})
    if len(years) < 3:
        return None

    selection_years = years[:-1]
    heldout_year = years[-1]
    key = f"budget_{budget:.2f}"
    cells = metrics.get("by_year", {})

    captures = {}

    for name in SIMPLE_METHODS:
        values = []
        for year in selection_years:
            value = _number(
                cells.get(str(year), {})
                .get(key, {})
                .get(name, {})
                .get("capture")
            )
            if value is None:
                return None
            values.append(value)

        captures[name] = sum(values) / len(values)

    chosen = max(
        SIMPLE_METHODS,
        key=lambda method: (
            round(captures[method], 4),
            -SIMPLE_METHODS.index(method),
        ),
    )

    final = cells.get(str(heldout_year), {}).get(key, {})
    chosen_row = final.get(chosen, {})
    oldest_row = final.get("oldest", {})

    result = {
        k: _number(chosen_row.get(k))
        for k in ("capture", "precision")
    }

    result["oldest_capture"] = _number(oldest_row.get("capture"))
    non_events = _number(chosen_row.get("observed_non_events"))

    if any(v is None for v in (*result.values(), non_events)):
        return None

    return {
        "selected_method": chosen,
        "selection_years": selection_years,
        "heldout_year": heldout_year,
        "selection_capture_means": captures,
        "holdout_capture": result["capture"],
        "holdout_precision": result["precision"],
        "holdout_oldest_capture": result["oldest_capture"],
        "holdout_observed_non_events": int(non_events),
        "same_as_all_year_champion":
            chosen == metrics.get("champion_method"),
    }


def robustness_rows(metrics: dict) -> pd.DataFrame:
    """Display previously measured robustness tests."""
    records = []

    scenarios = (
        metrics.get("robustness", {}).get("scenarios", {})
        if metrics else {}
    )

    for name, payload in scenarios.items():
        for method in ("champion", "lookup", "logistic"):
            measure = payload.get("methods", {}).get(method)
            if not measure:
                continue

            capture = _number(measure.get("capture_at_05"))
            change = _number(measure.get("capture_at_05_change"))

            records.append({
                "Test": name,
                "Method": method,
                "Capture@5%": capture,
                "Change (percentage points)":
                    None if change is None else round(100 * change, 2),
                "Selected-set overlap":
                    _number(measure.get("selection_overlap_at_05")),
                "Rank correlation":
                    _number(measure.get("spearman_rank_corr")),
            })

    return pd.DataFrame.from_records(
        records,
        columns=[
            "Test",
            "Method",
            "Capture@5%",
            "Change (percentage points)",
            "Selected-set overlap",
            "Rank correlation",
        ],
    )
