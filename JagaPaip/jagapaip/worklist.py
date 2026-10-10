"""Filtering, sorting, explanation, and export for the operational worklist.

These functions change what is shown. They never change rank or selection,
which come from ``ranking.build_worklist``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from jagapaip.ranking import SCORE_SOURCE_CONTRACT, SCORE_SOURCE_SUPPLIED
from jagapaip.schema import ACTION_INSPECT, ACTION_MONITOR, ACTION_PENDING, ACTION_RENEWAL

MAX_SEARCH_LENGTH = 64

PLAN_ALL = "All segments"
PLAN_FUNDED = "Funded only"
PLAN_UNFUNDED = "Not funded"
PLAN_STATUSES = (PLAN_FUNDED, PLAN_ALL, PLAN_UNFUNDED)

REVIEW_ALL = "All review states"
REVIEW_OPEN = "Needs review"
REVIEW_DONE = "Reviewed this session"
REVIEW_STATUSES = (REVIEW_ALL, REVIEW_OPEN, REVIEW_DONE)

PRIORITY_BY_ACTION = {
    ACTION_RENEWAL: "P1",
    ACTION_INSPECT: "P2",
    ACTION_MONITOR: "P3",
    ACTION_PENDING: "P9",
}
PRIORITY_LABELS = {
    "P1": "P1 — act first",
    "P2": "P2 — inspect",
    "P3": "P3 — monitor",
    "P9": "Pending decision engine",
}

SORT_OPTIONS = {
    "Planning rank": ("rank", True),
    "Priority, most urgent first": ("priority", True),
    "Risk score, highest first": ("predicted_risk", False),
    "Age, oldest first": ("age_years", False),
    "Recorded breaks, most first": ("historical_breaks", False),
    "Length, longest first": ("length_m", False),
    "Length, shortest first": ("length_m", True),
    "Install year, earliest first": ("install_year", True),
}


@dataclass
class Criteria:
    search: str = ""
    bands: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    zones: list[str] = field(default_factory=list)
    plan_status: str = PLAN_FUNDED
    review_status: str = REVIEW_ALL
    reviewed_ids: set[str] = field(default_factory=set)
    age_range: tuple[float, float] | None = None
    sort: str = "Planning rank"


def clean_search(text: object) -> str:
    value = "" if text is None else str(text)
    return value.strip()[:MAX_SEARCH_LENGTH]


def _allowed(values: list[str], available: pd.Series) -> list[str]:
    known = set(available.dropna().astype(str))
    return [value for value in values if str(value) in known]


def filter_worklist(plan: pd.DataFrame, criteria: Criteria) -> pd.DataFrame:
    """Apply validated filters. Unknown filter values are ignored, not errors."""
    view = plan
    search = clean_search(criteria.search)
    if search:
        view = view.loc[view["pipe_id"].astype(str).str.contains(search, case=False, na=False, regex=False)]
    bands = _allowed(criteria.bands, plan["risk_band"])
    if bands:
        view = view.loc[view["risk_band"].astype(str).isin(bands)]
    actions = _allowed(criteria.actions, plan["recommended_action"])
    if actions:
        view = view.loc[view["recommended_action"].astype(str).isin(actions)]
    if "material" in plan.columns:
        materials = _allowed(criteria.materials, plan["material"])
        if materials:
            view = view.loc[view["material"].astype(str).isin(materials)]
    if "zone" in plan.columns:
        zones = _allowed(criteria.zones, plan["zone"])
        if zones:
            view = view.loc[view["zone"].astype(str).isin(zones)]
    if criteria.age_range is not None and "age_years" in plan.columns:
        low, high = sorted(float(value) for value in criteria.age_range)
        age = pd.to_numeric(view["age_years"], errors="coerce")
        view = view.loc[age.between(low, high)]
    if criteria.plan_status == PLAN_FUNDED:
        view = view.loc[view["selected"]]
    elif criteria.plan_status == PLAN_UNFUNDED:
        view = view.loc[~view["selected"]]
    reviewed = {str(item) for item in criteria.reviewed_ids}
    if criteria.review_status == REVIEW_OPEN:
        view = view.loc[~view["pipe_id"].astype(str).isin(reviewed)]
    elif criteria.review_status == REVIEW_DONE:
        view = view.loc[view["pipe_id"].astype(str).isin(reviewed)]
    return sort_worklist(view, criteria.sort)


def sort_worklist(frame: pd.DataFrame, option: str) -> pd.DataFrame:
    """Stable display sort. Rank breaks ties so the order is deterministic."""
    column, ascending = SORT_OPTIONS.get(option, SORT_OPTIONS["Planning rank"])
    if column not in frame.columns:
        column, ascending = "rank", True
    if column == "rank":
        return frame.sort_values("rank", kind="mergesort")
    return frame.sort_values([column, "rank"], ascending=[ascending, True], kind="mergesort", na_position="last")


def priority_reason(row: pd.Series | dict) -> str:
    """One-line reason for the segment's position. States inputs, not causes."""
    get = row.get
    score = get("predicted_risk")
    if get("score_source") == SCORE_SOURCE_SUPPLIED:
        return f"Supplied model score {float(score):.3f}"
    if get("score_source") == SCORE_SOURCE_CONTRACT:
        facts = [f"champion percentile {float(score):.3f}"]
        breaks, age = get("historical_breaks"), get("age_years")
        if pd.notna(breaks):
            facts.append(f"{int(breaks)} prior {'break' if int(breaks) == 1 else 'breaks'}")
        if pd.notna(age):
            facts.append(f"age {int(round(float(age)))} yrs")
        return "Measured: " + " · ".join(facts)
    parts = []
    age = get("age_years")
    if pd.notna(age) and pd.notna(get("age_component")):
        parts.append((float(get("age_component")), f"age {int(round(float(age)))} yrs +{float(get('age_component')):.2f}"))
    if pd.notna(get("material_component")):
        parts.append((float(get("material_component")), f"{get('material_used', 'Unknown')} +{float(get('material_component')):.2f}"))
    breaks = get("historical_breaks")
    if pd.notna(breaks) and pd.notna(get("break_component")):
        noun = "break" if int(breaks) == 1 else "breaks"
        parts.append((float(get("break_component")), f"{int(breaks)} prior {noun} +{float(get('break_component')):.2f}"))
    else:
        parts.append((0.0, "break history not in source"))
    parts.sort(key=lambda item: -item[0])
    return "Heuristic: " + " · ".join(text for _, text in parts)


def priority_code(action: object) -> str:
    return PRIORITY_BY_ACTION.get(str(action), "P3")


def priority_label(action: object) -> str:
    return PRIORITY_LABELS.get(priority_code(action), PRIORITY_LABELS["P3"])


def location_text(zone: object) -> str:
    if zone is None or (isinstance(zone, float) and pd.isna(zone)):
        return "Location not recorded"
    text = str(zone).strip()
    if not text or text.lower() in {"nan", "none", "not recorded", "unknown"}:
        return "Location not recorded"
    return text


def evidence_line(row: pd.Series | dict) -> str:
    """Short recorded-fact summary. Not a cause statement."""
    get = row.get
    parts: list[str] = []
    material = get("material")
    if material is not None and not (isinstance(material, float) and pd.isna(material)):
        parts.append(str(material))
    age = get("age_years")
    if pd.notna(age):
        parts.append(f"{int(round(float(age)))} yrs")
    breaks = get("historical_breaks")
    if pd.notna(breaks):
        count = int(breaks)
        parts.append(f"{count} prior {'break' if count == 1 else 'breaks'}")
    else:
        parts.append("break history not in source")
    return " · ".join(parts)


def review_label(pipe_id: object, reviewed_ids: set[str] | None) -> str:
    return "Reviewed" if str(pipe_id) in (reviewed_ids or set()) else "Needs review"


def add_reasons(plan: pd.DataFrame) -> pd.DataFrame:
    frame = plan.copy()
    records = frame.to_dict(orient="records") if len(frame) else []
    frame["priority_reason"] = [priority_reason(row) for row in records]
    return frame


def annotate_worklist(plan: pd.DataFrame, reviewed_ids: set[str] | None = None) -> pd.DataFrame:
    """Add display columns. Rank and selection are left unchanged."""
    frame = add_reasons(plan)
    if frame.empty:
        frame["location"] = []
        frame["priority"] = []
        frame["priority_label"] = []
        frame["evidence"] = []
        frame["review_status"] = []
        return frame
    records = frame.to_dict(orient="records")
    frame["location"] = [location_text(row.get("zone")) for row in records]
    frame["priority"] = [priority_code(row.get("recommended_action")) for row in records]
    frame["priority_label"] = [priority_label(row.get("recommended_action")) for row in records]
    frame["evidence"] = [evidence_line(row) for row in records]
    frame["review_status"] = [review_label(row.get("pipe_id"), reviewed_ids) for row in records]
    return frame


EXPORT_COLUMNS = {
    "rank": "rank",
    "pipe_id": "pipe_id",
    "predicted_risk": "risk_score",
    "score_source": "score_source",
    "risk_band": "risk_band",
    "recommended_action": "recommended_action",
    "selected": "in_plan",
    "selection_reason": "budget_decision",
    "priority_reason": "priority_reason",
    "priority": "priority",
    "priority_label": "priority_label",
    "location": "location",
    "evidence": "evidence",
    "review_status": "review_status",
    "material": "material",
    "zone": "zone",
    "install_year": "install_year",
    "age_years": "age_years",
    "length_m": "length_m",
    "diameter_mm": "diameter_mm",
    "historical_breaks": "recorded_breaks_to_decision_year",
    "decision_year": "decision_year",
}


def export_frame(frame: pd.DataFrame) -> pd.DataFrame:
    present = [column for column in EXPORT_COLUMNS if column in frame.columns]
    return frame[present].rename(columns=EXPORT_COLUMNS)


def export_csv(frame: pd.DataFrame) -> bytes:
    return export_frame(frame).to_csv(index=False).encode("utf-8")
