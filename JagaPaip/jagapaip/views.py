"""Streamlit pages. Ranking and outcomes stay in the other modules."""

from __future__ import annotations

import html
import math
import textwrap

import pandas as pd
import streamlit as st

from jagapaip import charts
from jagapaip.proof import build_plan, features_for_year
from jagapaip.ranking import plan_summary
from jagapaip.schema import (
    ACTION_INSPECT,
    ACTION_MONITOR,
    ACTION_PENDING,
    ACTION_RENEWAL,
    BAND_HIGH,
    BAND_LOW,
    BAND_MODERATE,
    INSPECT_THRESHOLD,
    RENEWAL_THRESHOLD,
    STRATEGY_JAGAPAIP,
)

PAGES = [
    "Overview",
    "Risk Worklist",
    "Pipe Evidence",
    "Proof Mode",
    "Evaluation & Data Quality",
]

PAGE_SLUGS = {
    "overview": "Overview",
    "worklist": "Risk Worklist",
    "evidence": "Pipe Evidence",
    "proof": "Proof Mode",
    "evaluation": "Evaluation & Data Quality",
}

BAND_TONE = {BAND_HIGH: "high", BAND_MODERATE: "moderate", BAND_LOW: "low"}
ACTION_TONE = {ACTION_RENEWAL: "high", ACTION_INSPECT: "moderate", ACTION_MONITOR: "teal", ACTION_PENDING: "slate"}
ACTION_DOT = {ACTION_RENEWAL: "red", ACTION_INSPECT: "amber", ACTION_MONITOR: "teal", ACTION_PENDING: "slate"}
BAND_TEXT_COLOUR = {BAND_HIGH: "#B91C1C", BAND_MODERATE: "#B45309", BAND_LOW: "#047857"}
ACTION_TEXT_COLOUR = {ACTION_RENEWAL: "#B91C1C", ACTION_INSPECT: "#B45309", ACTION_MONITOR: "#0F766E", ACTION_PENDING: "#475569"}
SCORE_BAR_COLOUR = {BAND_HIGH: "#DC2626", BAND_MODERATE: "#F59E0B", BAND_LOW: "#10B981"}


# ---------------------------------------------------------------- helpers

def show_html(markup: str) -> None:
    """Render markup. Leading spaces would otherwise appear as a code block."""
    st.markdown(textwrap.dedent(markup).strip(), unsafe_allow_html=True)


def esc(value: object) -> str:
    return html.escape(str(value))


def operational_features(dataset: dict) -> pd.DataFrame:
    return features_for_year(dataset, int(dataset["meta"]["decision_year"]))


def slider_ceiling(kilometres: float, step: float = 0.1) -> float:
    steps = math.ceil(max(kilometres, 0.0) / step - 1e-9)
    return round(max(step, steps * step), 2)


def snap(value: float, step: float = 0.1) -> float:
    return round(round(value / step) * step, 2)


def km_text(metres: float) -> str:
    return f"{metres / 1000:.2f} km"


def missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def show_text(value: object, digits: int | None = None, suffix: str = "") -> str:
    if missing(value):
        return "Not in source"
    if digits is None:
        return f"{value}{suffix}"
    return f"{float(value):.{digits}f}{suffix}"


def score_source_label(plan: pd.DataFrame) -> str:
    if plan.empty or "score_source" not in plan.columns:
        return "Unavailable"
    sources = set(plan["score_source"].dropna().unique())
    if sources == {"contract_champion"}:
        return "Measured champion (Contract B)"
    if sources == {"supplied_prediction"}:
        return "Supplied predictions"
    if "supplied_prediction" in sources:
        return "Predictions + heuristic fill"
    return "Screening heuristic"


def scores_in_unit_range(plan: pd.DataFrame) -> bool:
    scores = pd.to_numeric(plan.get("predicted_risk"), errors="coerce").dropna()
    return bool(len(scores)) and float(scores.min()) >= 0 and float(scores.max()) <= 1


# ---------------------------------------------------------------- components

def chip(text: str, tone: str = "", dot: str | None = None, muted: str | None = None) -> str:
    dot_html = f"<span class='dot {dot}'></span>" if dot else ""
    muted_html = f"<span class='muted'>{esc(muted)}</span>" if muted else ""
    return f"<span class='chip {tone}'>{dot_html}{muted_html}{esc(text)}</span>"


def data_chip(meta: dict) -> str:
    if meta["mode"] == "demo":
        return chip("DEMO DATA — NOT REAL UTILITY DATA", "demo", "amber")
    if meta.get("demonstrator"):
        return chip(meta["status_title"], "demo", "amber")
    return chip(meta["status_title"], "live", "teal")


def page_header(title: str, subtitle: str, chips: list[str]) -> None:
    show_html(
        f"""
        <div class="jp-header">
          <h1>{esc(title)}</h1>
          <p class="jp-subtitle">{esc(subtitle)}</p>
          <div class="jp-chips">{''.join(chips)}</div>
        </div>
        """
    )


def kpi_grid(items: list[dict]) -> None:
    blocks = []
    for item in items:
        value = item.get("value")
        unavailable = value is None
        value_html = esc(item.get("fallback", "Unavailable")) if unavailable else esc(value)
        if not unavailable and item.get("unit"):
            value_html += f"<small>{esc(item['unit'])}</small>"
        dot = f"<span class='dot {item['dot']}'></span>" if item.get("dot") else ""
        blocks.append(
            f"<div class='jp-kpi' title='{esc(item.get('help', ''))}'>"
            f"<div class='label'>{dot}{esc(item['label'])}</div>"
            f"<div class='value{' unavailable' if unavailable else ''}'>{value_html}</div>"
            f"<div class='note'>{esc(item.get('note', ''))}</div>"
            "</div>"
        )
    show_html(f"<div class='jp-kpis'>{''.join(blocks)}</div>")


def panel(key: str):
    return st.container(key=f"panel_{key}")


def panel_head(title: str, subtitle: str = "", meta: str = "") -> None:
    sub = f"<p class='jp-panel-sub'>{esc(subtitle)}</p>" if subtitle else ""
    meta_html = f"<div class='jp-panel-meta'>{esc(meta)}</div>" if meta else ""
    show_html(
        f"<div class='jp-panel-head'><div><p class='jp-panel-title'>{esc(title)}</p>{sub}</div>{meta_html}</div>"
    )


def notice(title: str, lines: list[str] | None = None, warn: bool = False) -> None:
    items = ""
    if lines:
        items = "<ul>" + "".join(f"<li>{esc(line)}</li>" for line in lines) + "</ul>"
    kind = "jp-notice warn" if warn else "jp-notice"
    show_html(f"<div class='{kind}'><div><strong>{esc(title)}</strong>{items}</div></div>")


def fact_list(pairs: list[tuple[str, str]]) -> None:
    rows = "".join(f"<div class='jp-fact'><span>{esc(label)}</span><strong>{esc(value)}</strong></div>" for label, value in pairs)
    show_html(f"<div>{rows}</div>")


def pill(text: str, tone: str) -> str:
    return f"<span class='pill {tone}'>{esc(text)}</span>"


def show_chart(figure) -> None:
    st.plotly_chart(figure, theme=None, width="stretch", config={"displayModeBar": False})


def limitation_lines(meta: dict) -> list[str]:
    lines = [
        meta["status_detail"],
        meta["score_note"],
        meta["length_note"] + " Monetary replacement cost is not invented. The budget is a length of pipe unless a cost column is later wired in by the team.",
        "Ranking and budget selection use information available at the decision year. Breaks after that year are not an input.",
        "If a file is City of Kitchener data, it demonstrates the method only. It does not establish effectiveness for Malaysian utilities. A Malaysian pilot needs records from the local utility.",
    ]
    if meta["mode"] == "demo":
        lines.append(
            "Demo breaks were simulated from age and material, which are also inputs to the screening score. Do not read the demo as a performance result."
        )
    return lines


# ---------------------------------------------------------------- tables

WORKLIST_CONFIG = {
    "Rank": st.column_config.NumberColumn("Rank", format="%d", width="small", help="Planning order. The budget is spent from rank 1 downwards."),
    "Length (m)": st.column_config.NumberColumn("Length (m)", format="%.0f", help="Segment length. This is what the budget spends."),
    "Age (years)": st.column_config.NumberColumn("Age (years)", format="%.0f", help="Decision year minus install year."),
    "Installed": st.column_config.NumberColumn("Installed", format="%d"),
    "Diameter (mm)": st.column_config.NumberColumn("Diameter (mm)", format="%.0f"),
    "Recorded breaks": st.column_config.NumberColumn(
        "Recorded breaks",
        format="%.0f",
        help="Breaks dated on or before the decision year. Later breaks are not included.",
    ),
    "In plan": st.column_config.TextColumn("In plan", width="small", help="Yes when the segment fits the current length budget."),
    "Budget decision": st.column_config.TextColumn("Budget decision", help="Why the length rule included or skipped this segment."),
}


def worklist_config(plan: pd.DataFrame) -> dict:
    config = dict(WORKLIST_CONFIG)
    help_text = "Priority score for the JagaPaip queue. Higher is earlier. It is not automatically a probability of failure."
    if scores_in_unit_range(plan):
        config["Risk score"] = st.column_config.ProgressColumn("Risk score", format="%.3f", min_value=0.0, max_value=1.0, help=help_text)
    else:
        config["Risk score"] = st.column_config.NumberColumn("Risk score", format="%.3f", help=help_text)
    return config


def worklist_frame(plan: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Rank": plan["rank"],
            "Pipe ID": plan["pipe_id"],
            "Risk score": plan["predicted_risk"],
            "Risk band": plan["risk_band"],
            "Recommended action": plan["recommended_action"],
            "In plan": plan["selected"].map(lambda flag: "Yes" if bool(flag) else "No"),
            "Material": plan["material"],
            "Age (years)": plan["age_years"],
            "Length (m)": plan["length_m"],
            "Recorded breaks": plan["historical_breaks"],
            "Zone": plan["zone"],
            "Installed": plan["install_year"],
            "Diameter (mm)": plan["diameter_mm"],
            "Budget decision": plan["selection_reason"],
        }
    )


def table_height(rows: int, cap: int = 520) -> int:
    return int(min(cap, 38 + 35 * max(rows, 1) + 2))


def styled(frame: pd.DataFrame):
    """Colour the risk band and action text. Values are unchanged."""

    def band(value):
        colour = BAND_TEXT_COLOUR.get(value)
        return f"color: {colour}; font-weight: 600" if colour else ""

    def action(value):
        colour = ACTION_TEXT_COLOUR.get(value)
        return f"color: {colour}; font-weight: 600" if colour else ""

    styler = frame.style
    for column, rule in (("Risk band", band), ("Action", action), ("Recommended action", action)):
        if column in frame.columns:
            styler = styler.map(rule, subset=[column])
    return styler


def priority_table(rows: pd.DataFrame) -> None:
    body = []
    for row in rows.itertuples(index=False):
        score = float(row.predicted_risk)
        width = max(0.0, min(1.0, score)) * 100
        bar_colour = SCORE_BAR_COLOUR.get(row.risk_band, "#94A3B8")
        zone = "" if missing(row.zone) else f"<div class='sub'>{esc(row.zone)}</div>"
        body.append(
            "<tr>"
            f"<td class='rank'>{int(row.rank)}</td>"
            f"<td><div class='pipe'>{esc(row.pipe_id)}</div>{zone}</td>"
            f"<td>{esc(show_text(row.material))}</td>"
            f"<td class='num'>{esc(show_text(row.age_years, 0))}</td>"
            f"<td class='num'>{esc(show_text(row.length_m, 0))}</td>"
            f"<td class='num'>{esc(show_text(row.historical_breaks, 0))}</td>"
            f"<td><div class='jp-score'><div class='bar'><div style='width:{width:.0f}%;background:{bar_colour}'></div></div>"
            f"<span>{score:.3f}</span></div></td>"
            f"<td>{pill(row.risk_band, BAND_TONE.get(row.risk_band, 'slate'))}</td>"
            f"<td>{pill(row.recommended_action, ACTION_TONE.get(row.recommended_action, 'slate'))}</td>"
            "</tr>"
        )
    show_html(
        "<div class='jp-table-wrap'><table class='jp-table'><thead><tr>"
        "<th>Rank</th><th>Pipe segment</th><th>Material</th>"
        "<th class='num'>Age (yrs)</th><th class='num'>Length (m)</th><th class='num'>Recorded breaks</th>"
        "<th class='num'>Risk score</th><th>Risk band</th><th>Recommended action</th>"
        f"</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


# ---------------------------------------------------------------- shell

def render_app(dataset: dict) -> None:
    features = operational_features(dataset)
    network_m = float(features["length_m"].sum()) if len(features) else 0.0
    page, budget_km, summary_slot = render_sidebar(dataset["meta"], network_m)
    plan = build_plan(features, float(budget_km) * 1000, STRATEGY_JAGAPAIP)
    summary = plan_summary(plan, float(budget_km) * 1000)
    summary_slot.markdown(sidebar_stats(summary), unsafe_allow_html=True)
    from jagapaip.workflows import page_evaluation, page_proof, page_worklist

    pages = {
        "Overview": lambda: page_overview(dataset, plan, summary),
        "Risk Worklist": lambda: page_worklist(dataset, plan, summary),
        "Pipe Evidence": lambda: page_evidence(dataset, plan),
        "Proof Mode": lambda: page_proof(dataset),
        "Evaluation & Data Quality": lambda: page_evaluation(dataset, plan),
    }
    try:
        pages[page]()
    except Exception as exc:  # noqa: BLE001 - keep the shell up so the other pages still work
        st.error(f"{page} could not be drawn. The other sections are unchanged.")
        st.exception(exc)


def go_to(page: str, **state) -> None:
    """Button callback. Runs before widgets are created, so it may set their keys."""
    if page in PAGES:
        st.session_state.page = page
    for key, value in state.items():
        st.session_state[key] = value


def step_title(number: int, title: str, subtitle: str) -> None:
    show_html(
        f"<div class='jp-panel-head'><div><p class='jp-panel-title'><span class='jp-step'>{number}</span>{esc(title)}</p>"
        f"<p class='jp-panel-sub'>{esc(subtitle)}</p></div></div>"
    )


def sidebar_stats(summary: dict) -> str:
    rows = [
        ("Funded length", km_text(summary["selected_m"])),
        ("Segments funded", f"{summary['selected_segments']:,}"),
        ("Unspent", km_text(summary["unspent_m"])),
        ("Marginal segment", summary["marginal_pipe_id"] or "None"),
    ]
    inner = "".join(f"<div class='jp-side-row'><span>{esc(k)}</span><strong>{esc(v)}</strong></div>" for k, v in rows)
    return f"<div class='jp-side-stats'>{inner}</div>"


def render_sidebar(meta: dict, network_m: float):
    with st.sidebar:
        show_html(
            """
            <div class="jp-brand">
              <div class="jp-mark">JP</div>
              <div>
                <div class="jp-name">JagaPaip</div>
                <div class="jp-tag">Know which pipe first.</div>
              </div>
            </div>
            """
        )
        show_html("<div class='jp-side-label'>Workspace</div>")
        if "page" not in st.session_state:
            requested = PAGE_SLUGS.get(str(st.query_params.get("page", "")).lower())
            if requested:
                st.session_state.page = requested
        page = st.radio("Navigate", PAGES, label_visibility="collapsed", key="page")
        st.divider()
        show_html("<div class='jp-side-label'>Operational budget</div>")
        ceiling = slider_ceiling(network_m / 1000 if network_m else 0.1)
        if "budget_km" not in st.session_state:
            network_km = network_m / 1000 if network_m else 0.0
            default = min(ceiling, 5.0) if network_km >= 50 else min(ceiling, max(0.2, network_km * 0.20))
            st.session_state.budget_km = snap(default)
        if st.session_state.budget_km > ceiling:
            st.session_state.budget_km = ceiling
        budget_km = st.slider(
            "Network-length budget (km)",
            min_value=0.0,
            max_value=ceiling,
            step=0.1,
            key="budget_km",
            help="The plan is rebuilt in rank order and stops at the first segment that does not fit. No currency value is invented.",
        )
        summary_slot = st.empty()
        st.divider()
        show_html("<div class='jp-side-label'>Data source</div>")
        if meta["mode"] == "demo":
            show_html("<div class='jp-side-status'><span class='dot amber'></span><span>DEMO DATA — NOT REAL UTILITY DATA</span></div>")
        else:
            show_html(f"<div class='jp-side-status'><span class='dot teal'></span><span>{esc(meta['status_title'])}</span></div>")
        st.caption(f"Decision year {meta['decision_year']}. Runs locally with no API key or internet connection.")
        st.caption(
            "City of Kitchener data, if connected, is a method demonstrator. It does not establish effectiveness for Malaysian utilities."
        )
    return page, float(budget_km), summary_slot


def standard_chips(meta: dict, budget_m: float | None = None) -> list[str]:
    chips = [data_chip(meta), chip(str(meta["decision_year"]), dot="slate", muted="Decision year ")]
    if budget_m is not None:
        chips.append(chip(km_text(budget_m), dot="teal", muted="Budget "))
    return chips


# ---------------------------------------------------------------- Overview

def page_overview(dataset: dict, plan: pd.DataFrame, summary: dict) -> None:
    meta = dataset["meta"]
    source = score_source_label(plan)
    page_header(
        "Network Overview",
        "Budget-aware pipe intervention planning. Every in-service segment is ranked by risk, "
        "then the highest priorities that fit the available length budget are put forward for action.",
        standard_chips(meta, summary["budget_m"]) + [chip(source, dot="slate", muted="Scores ")],
    )
    if meta["mode"] == "demo":
        notice(
            "DEMO DATA — NOT REAL UTILITY DATA",
            [
                "This synthetic network exists so the interface can be demonstrated before team data files are added.",
                "Scores are a screening heuristic, not a validated model. No result on this screen is a utility finding.",
            ],
            warn=True,
        )
    elif meta.get("demonstrator"):
        notice(
            "KITCHENER OPEN DATA — METHOD DEMONSTRATOR",
            [
                "These pipes and breaks come from City of Kitchener open data prepared by Member 1. They are not Malaysian utility records.",
                (
                    "Scores are the measured champion from fold_predictions (Contract B); Proof Mode numbers come from metrics.json. "
                    "This does not establish effectiveness for Malaysian utilities."
                    if meta.get("contract_mode")
                    else "No trained model or metrics.json was in the handoff. Scores are a screening heuristic. This does not establish effectiveness for any utility."
                ),
            ],
            warn=True,
        )
    render_tour(plan)

    actions = summary["actions"]
    budget_m = summary["budget_m"]
    utilisation = None if budget_m <= 0 else 100 * summary["selected_m"] / budget_m
    kpi_grid(
        [
            {
                "label": "Network length",
                "value": f"{summary['network_m'] / 1000:,.2f}" if summary["candidates"] else None,
                "unit": "km",
                "note": f"In service at the end of {meta['decision_year']}. Not a replacement cost.",
                "dot": "slate",
            },
            {
                "label": "Pipe segments",
                "value": f"{summary['candidates']:,}" if summary["candidates"] else None,
                "note": (
                    f"{summary['high_risk_segments']:,} in the top 5% of the champion ranking."
                    if meta.get("contract_mode")
                    else f"{summary['high_risk_segments']:,} high-risk (score {RENEWAL_THRESHOLD:.2f} or above)."
                ),
                "dot": "red" if summary["high_risk_segments"] else "slate",
            },
            {
                "label": "Planned interventions",
                "value": f"{summary['selected_segments']:,}",
                "note": (
                    f"{actions.get(ACTION_RENEWAL, 0)} renewal review · {actions.get(ACTION_INSPECT, 0)} inspect · "
                    f"{actions.get(ACTION_MONITOR, 0)} monitor"
                    + (f" · {actions[ACTION_PENDING]} awaiting decision engine" if actions.get(ACTION_PENDING) else "")
                ),
                "dot": "teal",
            },
            {
                "label": "Budget utilisation",
                "value": None if utilisation is None else f"{utilisation:.0f}",
                "unit": "%",
                "fallback": "No budget set",
                "note": (
                    "Set a length budget in the sidebar."
                    if utilisation is None
                    else f"{km_text(summary['selected_m'])} funded of {km_text(budget_m)}."
                ),
                "dot": "teal",
            },
        ]
    )

    left, right = st.columns([3, 2], gap="medium")
    with left:
        with panel("risk_distribution"):
            panel_head(
                "Risk distribution",
                f"Segments by risk score. Bands: Inspect from {INSPECT_THRESHOLD:.2f}, Renewal Review from {RENEWAL_THRESHOLD:.2f}.",
                meta=f"{summary['candidates']:,} segments",
            )
            if plan.empty:
                st.info("No in-service segments are available for this decision year.")
            else:
                show_chart(charts.risk_distribution_chart(plan))
    with right:
        with panel("budget_summary"):
            panel_head("Budget allocation", "Length budget spent in rank order.")
            render_budget_summary(summary, utilisation)

    with panel("priority_actions"):
        funded = plan.loc[plan["selected"]].sort_values("rank")
        shown = funded.head(10)
        panel_head(
            "Priority actions",
            "Highest-ranked segments that fit the current budget. Open Risk Worklist for the full register, filters, and export.",
            meta=f"Showing {len(shown)} of {len(funded)} funded" if len(funded) else "",
        )
        if funded.empty:
            st.info("No segment fits this length budget yet. Increase the budget in the sidebar to fund the first priorities.")
        else:
            priority_table(shown)

    notice(
        "Data and model confidence",
        [
            meta["score_note"],
            "Ranking uses only facts available at the decision year. Later breaks are never an input.",
            "Model performance is not yet evaluated on this screen. See Evaluation & Data Quality for what the files report.",
        ],
        warn=meta["mode"] == "demo",
    )
    with st.expander("Method and data limitations"):
        st.markdown(
            """
            1. Each in-service segment receives a score: the measured champion's risk percentile from Contract B when it is loaded, otherwise the screening heuristic.
            2. JagaPaip sorts by score, highest first. With Contract B, ties go to pipe ID (the team contract); with the heuristic, to more recorded breaks, then greater age, then pipe ID.
            3. The budget walks down that list and stops at the first segment that does not fit, the same rule as metrics.json and the decision engine.
            4. Recommended action comes from the decision engine (Contract C) when Contract B is loaded; otherwise it is a band on the heuristic score: Renewal Review at 0.70 or above, Inspect at 0.45 or above, otherwise Monitor.
            """
        )
        for line in limitation_lines(meta):
            st.markdown(f"- {line}")


TOUR = [
    ("The problem", "Budgets cover a fraction of the network. Which pipes first?", None, "You are here"),
    ("Change the budget", "Move the sidebar slider. The plan and every total are recalculated.", "Risk Worklist", "Open worklist"),
    ("Inspect a pipe", "See recorded facts kept apart from the score and its reasons.", "Pipe Evidence", "Inspect top pipe"),
    ("Test on the past", "Plan for a past year, then reveal what actually broke.", "Proof Mode", "Open Proof Mode"),
    ("Check the evidence", "See where every number comes from and what is not claimed.", "Evaluation & Data Quality", "Open evidence"),
]


def render_tour(plan: pd.DataFrame) -> None:
    if st.session_state.get("tour_hidden"):
        st.button("Show guided demo", on_click=go_to, args=("",), kwargs={"tour_hidden": False}, key="tour_show")
        return
    with panel("tour"):
        head, close = st.columns([6, 1])
        with head:
            panel_head("Guided demo", "Five steps, about three minutes. Each button opens the page with a sensible starting point.")
        with close:
            st.button("Hide", on_click=go_to, args=("",), kwargs={"tour_hidden": True}, key="tour_hide", width="stretch")
        top = plan.sort_values("rank").iloc[0]["pipe_id"] if len(plan) else None
        columns = st.columns(len(TOUR), gap="small")
        for index, (column, (title, text, target, label)) in enumerate(zip(columns, TOUR), start=1):
            with column:
                show_html(
                    f"<p class='jp-panel-title' style='font-size:0.92rem'><span class='jp-step'>{index}</span>{esc(title)}</p>"
                    f"<p class='jp-panel-sub' style='min-height:3.9em'>{esc(text)}</p>"
                )
                if target is None:
                    st.button(label, disabled=True, key=f"tour_{index}", width="stretch")
                else:
                    extra = {"evidence_pipe": str(top)} if target == "Pipe Evidence" and top is not None else {}
                    st.button(label, on_click=go_to, args=(target,), kwargs=extra, key=f"tour_{index}", width="stretch")


def render_budget_summary(summary: dict, utilisation: float | None) -> None:
    budget_m = summary["budget_m"]
    width = 0 if utilisation is None else max(0.0, min(100.0, utilisation))
    big = "No budget set" if utilisation is None else f"{utilisation:.0f}<small>% used</small>"
    show_html(
        f"""
        <div class="jp-big">{big}</div>
        <div style="margin-top:10px" class="jp-meter"><div style="width:{width:.1f}%"></div></div>
        <div class="jp-meter-labels"><span>{esc(km_text(summary['selected_m']))} funded</span><span>{esc(km_text(budget_m))} budget</span></div>
        """
    )
    high = summary["high_risk_segments"]
    fact_list(
        [
            ("Unspent length", km_text(summary["unspent_m"])),
            ("Share of network funded", "Unavailable" if summary["network_m"] <= 0 else f"{100 * summary['selected_m'] / summary['network_m']:.1f}%"),
            ("High-risk segments funded", f"{summary['high_risk_in_plan']} of {high}" if high else "None in network"),
            ("Marginal segment", summary["marginal_pipe_id"] or "None"),
        ]
    )
    rows = []
    shown = [ACTION_RENEWAL, ACTION_INSPECT, ACTION_MONITOR] + ([ACTION_PENDING] if summary["actions"].get(ACTION_PENDING) else [])
    for action in shown:
        count = summary["actions"].get(action, 0)
        rows.append(
            f"<div class='jp-action-row'><span class='name'><span class='dot {ACTION_DOT[action]}'></span>{esc(action)}</span>"
            f"<span class='count'>{count}</span></div>"
        )
    show_html("<p class='jp-panel-title' style='font-size:0.95rem;margin-top:4px'>Funded by recommended action</p>" + "".join(rows))


# ---------------------------------------------------------------- Pipe Evidence

def recorded_history(dataset: dict, pipe_id: str, decision_year: int) -> pd.DataFrame | None:
    breaks = dataset["breaks"]
    if breaks is None:
        return None
    history = breaks.loc[breaks["pipe_id"].astype(str) == str(pipe_id)].copy()
    if history.empty:
        return history
    years = pd.to_numeric(history["break_year"], errors="coerce")
    return history.loc[years.notna() & (years <= decision_year)]


def page_evidence(dataset: dict, plan: pd.DataFrame) -> None:
    meta = dataset["meta"]
    page_header(
        "Pipe Evidence",
        "Recorded facts for one segment, kept separate from the score and the recommended action.",
        standard_chips(meta),
    )
    if plan.empty:
        st.info("No in-service segments are available for this decision year.")
        return
    ordered = plan.sort_values("rank")
    labels = {
        row.pipe_id: f"#{int(row.rank)}  ·  {row.pipe_id}  ·  {row.material}  ·  score {row.predicted_risk:.3f}  ·  {row.recommended_action}"
        for row in ordered.itertuples(index=False)
    }
    if st.session_state.get("evidence_pipe") not in labels:
        st.session_state.evidence_pipe = next(iter(labels))
    with panel("pipe_select"):
        pipe_id = st.selectbox(
            "Pipe segment",
            list(labels),
            format_func=lambda item: labels[item],
            help="Listed in planning rank order. Type to search by pipe ID.",
            key="evidence_pipe",
        )
        row = plan.loc[plan["pipe_id"] == pipe_id].iloc[0]
        in_plan = pill("In the current plan", "teal") if row.selected else pill("Outside the current plan", "slate")
        show_html(
            f"<div style='display:flex;gap:8px;flex-wrap:wrap;align-items:center'>"
            f"{pill(f'{row.risk_band} risk', BAND_TONE.get(row.risk_band, 'slate'))}"
            f"{pill(row.recommended_action, ACTION_TONE.get(row.recommended_action, 'slate'))}{in_plan}"
            f"<span class='jp-foot'>{esc(row.selection_reason)}</span></div>"
        )

    kpi_grid(
        [
            {"label": "Risk score", "value": f"{row.predicted_risk:.3f}", "note": score_source_label(plan.loc[plan['pipe_id'] == pipe_id]), "dot": {"High": "red", "Moderate": "amber", "Low": "green"}.get(row.risk_band, "slate")},
            {"label": "Planning rank", "value": f"{int(row['rank'])}", "note": f"of {len(plan):,} segments.", "dot": "slate"},
            {"label": "Length", "value": None if missing(row.length_m) else f"{float(row.length_m):,.0f}", "unit": "m", "note": "What this segment costs the length budget.", "dot": "slate"},
            {"label": "Recorded breaks", "value": None if missing(row.historical_breaks) else f"{int(row.historical_breaks)}", "fallback": "Not in source", "note": f"On or before {meta['decision_year']}.", "dot": "slate"},
        ]
    )

    left, right = st.columns(2, gap="medium")
    with left:
        with panel("facts"):
            panel_head("Known facts", "Copied from the loaded data. Nothing here is predicted.")
            fact_list(
                [
                    ("Pipe ID", str(row.pipe_id)),
                    ("Zone", show_text(row.zone)),
                    ("Material", show_text(row.material)),
                    ("Installed", show_text(row.install_year, 0)),
                    ("Age at decision year", show_text(row.age_years, 0, " years")),
                    ("Length", show_text(row.length_m, 0, " m")),
                    ("Diameter", show_text(row.diameter_mm, 0, " mm")),
                    ("Recorded breaks through decision year", show_text(row.historical_breaks, 0)),
                    ("Decision year", str(meta["decision_year"])),
                ]
            )
            st.caption("Not in this source: soil, pressure, traffic loading, water quality, and monetary cost.")
    with right:
        with panel("assessment"):
            panel_head("Model assessment", "A ranking aid derived from the facts. Not an observation and not a cause.")
            source = "Screening heuristic" if row.score_source == "screening_heuristic" else "Supplied prediction"
            fact_list(
                [
                    ("Risk score", f"{row.predicted_risk:.3f}"),
                    ("Score source", source),
                    ("Risk band", str(row.risk_band)),
                    ("Recommended action", str(row.recommended_action)),
                    ("Budget decision", str(row.selection_reason)),
                ]
            )
            show_html(f"<p class='jp-panel-sub' style='color:#334155'>{esc(row.explanation)}</p>")

    chart_left, chart_right = st.columns(2, gap="medium")
    with chart_left:
        with panel("components"):
            panel_head("Score components", "What entered the screening score, in points.")
            component = charts.component_chart(row)
            if component is None:
                st.info("This score was supplied by fold predictions. JagaPaip does not invent an age, material, or break contribution for it.")
            else:
                show_chart(component)
                st.caption("Points explain the heuristic only. They do not show that a factor caused a break.")
    with chart_right:
        with panel("history"):
            panel_head("Recorded break history", f"Breaks in the ledger on or before {meta['decision_year']}.")
            history = recorded_history(dataset, str(pipe_id), int(meta["decision_year"]))
            if history is None:
                st.info("This source has no year-level break ledger, so individual break years cannot be shown.")
            elif history.empty:
                st.info(f"No recorded breaks for {pipe_id} on or before {meta['decision_year']}.")
            else:
                show_chart(charts.break_history_chart(history))
                st.caption("These are dates in the loaded ledger. A date is not a cause.")
