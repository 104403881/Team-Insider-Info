"""Risk Worklist, Proof Mode, and Evaluation pages.

Decision logic lives in ranking, worklist, backtest, and quality. This module
only lays out their results with the shared components in ``views``.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from jagapaip import charts
from jagapaip.backtest import CAPTURE_FRACTION, run_backtest
from jagapaip.contract_proof import (
    across_years,
    contract_budgets,
    contract_plans,
    contract_years,
    metrics_cell,
    plan_mismatches,
    year_interval,
)
from jagapaip.proof import (
    available_evaluation_years,
    build_plan,
    compare_plans,
    difference_rows,
    features_for_year,
)
from jagapaip.quality import INFO, MISSING, PASS, WARN, field_validation_needs, provenance, run_checks
from jagapaip.schema import (
    ACTION_INSPECT,
    ACTION_MONITOR,
    ACTION_RENEWAL,
    BAND_HIGH,
    BAND_LOW,
    BAND_MODERATE,
    CONTRACT_CHAMPION,
    CONTRACT_OLDEST,
    PROOF_HORIZON_YEARS,
    STRATEGY_JAGAPAIP,
    STRATEGY_OLDEST,
)
from jagapaip.views import (
    esc,
    fact_list,
    go_to,
    km_text,
    kpi_grid,
    notice,
    page_header,
    panel,
    panel_head,
    pill,
    scores_in_unit_range,
    score_source_label,
    show_chart,
    show_html,
    show_text,
    slider_ceiling,
    snap,
    standard_chips,
    step_title,
    styled,
    table_height,
)
from jagapaip.worklist import (
    PLAN_FUNDED,
    PLAN_STATUSES,
    REVIEW_ALL,
    REVIEW_STATUSES,
    SORT_OPTIONS,
    Criteria,
    annotate_worklist,
    export_csv,
    filter_worklist,
)

# ---------------------------------------------------------------- Risk Worklist

def worklist_columns(plan: pd.DataFrame) -> dict:
    help_score = "Priority score for the JagaPaip queue. Higher is earlier. It is not automatically a probability of failure."
    score = (
        st.column_config.ProgressColumn("Risk score", format="%.3f", min_value=0.0, max_value=1.0, help=help_score)
        if scores_in_unit_range(plan)
        else st.column_config.NumberColumn("Risk score", format="%.3f", help=help_score)
    )
    return {
        "Rank": st.column_config.NumberColumn("Rank", format="%d", width="small", help="Planning order. The budget is spent from rank 1 downwards."),
        "Pipe ID": st.column_config.TextColumn("Pipe ID", width="small"),
        "Location": st.column_config.TextColumn("Location", help="Pressure zone or district from the loaded inventory."),
        "Risk score": score,
        "Risk band": st.column_config.TextColumn("Risk category", width="small"),
        "Priority": st.column_config.TextColumn("Priority", width="small", help="P1 Renewal Review, P2 Inspect, P3 Monitor. Follows the recommended action."),
        "Evidence": st.column_config.TextColumn("Evidence", width="large", help="Recorded facts used in the score. Not a cause of failure."),
        "Recommended action": st.column_config.TextColumn("Recommended action", help="Renewal Review at 0.70 or above, Inspect at 0.45 or above, otherwise Monitor."),
        "In plan": st.column_config.TextColumn("In plan", width="small", help="Yes when the segment fits the current length budget."),
        "Review": st.column_config.TextColumn("Review", width="small", help="Session-only. Marks are not saved to disk and are not an outcome."),
        "Why prioritised": st.column_config.TextColumn("Why prioritised", width="large", help="Inputs that produced the score, largest first. Not a cause of failure."),
        "Length (m)": st.column_config.NumberColumn("Length (m)", format="%.0f", help="What this segment costs the length budget."),
        "Age (years)": st.column_config.NumberColumn("Age", format="%.0f", help="Decision year minus install year."),
        "Recorded breaks": st.column_config.NumberColumn("Prior breaks", format="%.0f", help="Breaks dated on or before the decision year."),
        "Material": st.column_config.TextColumn("Material"),
        "Installed": st.column_config.NumberColumn("Installed", format="%d"),
        "Diameter (mm)": st.column_config.NumberColumn("Diameter (mm)", format="%.0f"),
        "Budget decision": st.column_config.TextColumn("Budget decision", help="Why the length rule included or skipped this segment."),
    }


def register_frame(view: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Rank": view["rank"],
            "Pipe ID": view["pipe_id"],
            "Location": view["location"],
            "Risk score": view["predicted_risk"],
            "Risk band": view["risk_band"],
            "Priority": view["priority"],
            "Evidence": view["evidence"],
            "Recommended action": view["recommended_action"],
            "In plan": view["selected"].map(lambda flag: "Yes" if bool(flag) else "No"),
            "Review": view["review_status"],
            "Why prioritised": view["priority_reason"],
            "Length (m)": view["length_m"],
            "Age (years)": view["age_years"],
            "Recorded breaks": view["historical_breaks"],
            "Material": view["material"],
            "Installed": view["install_year"],
            "Diameter (mm)": view["diameter_mm"],
            "Budget decision": view["selection_reason"],
        }
    )


def page_worklist(dataset: dict, plan: pd.DataFrame, summary: dict) -> None:
    meta = dataset["meta"]
    page_header(
        "Risk Worklist",
        "Every in-service segment in planning order. The sidebar budget re-runs selection; filters and sorting only change what you see.",
        standard_chips(meta, summary["budget_m"]) + [st_chip_scores(plan)],
    )
    network_m = summary["network_m"]
    share = None if network_m <= 0 else 100 * summary["selected_m"] / network_m
    reviewed = reviewed_ids()
    kpi_grid(
        [
            {"label": "Selected segments", "value": f"{summary['selected_segments']:,}", "note": f"of {summary['candidates']:,} ranked segments.", "dot": "teal"},
            {"label": "Selected network length", "value": f"{summary['selected_m'] / 1000:.2f}", "unit": "km",
             "note": "Share of network unavailable." if share is None else f"{share:.1f}% of the {km_text(network_m)} network.", "dot": "teal"},
            {"label": "Budget remaining", "value": f"{summary['unspent_m'] / 1000:.2f}", "unit": "km",
             "note": f"of {km_text(summary['budget_m'])}. Every unselected segment is longer than this.", "dot": "amber"},
            {"label": "Reviewed this session", "value": f"{len(reviewed):,}", "note": "Operator marks only. They are not saved and are not outcomes.", "dot": "slate"},
        ]
    )
    if plan.empty:
        st.info("No ranked segments are available for this decision year.")
        return

    plan = annotate_worklist(plan, reviewed)
    with panel("budget_fill"):
        panel_head(
            "How the budget fills",
            "Cumulative selected length as the budget walks down the ranked list. Flat steps are segments skipped because they did not fit.",
        )
        show_chart(charts.budget_walk_chart(plan, summary["budget_m"]))

    with panel("register"):
        panel_head("Pipe register", "Search by pipe ID, filter, and sort. Select a row to see why it is prioritised.")
        row1 = st.columns([1.3, 1, 1, 1], gap="small")
        with row1[0]:
            search = st.text_input("Search pipe ID", placeholder="e.g. JP-1018", max_chars=64, key="wl_search",
                                   help="Case-insensitive match on pipe ID. Filters the table only.")
        with row1[1]:
            bands = st.multiselect("Risk band", [BAND_HIGH, BAND_MODERATE, BAND_LOW], placeholder="All bands", key="wl_bands")
        with row1[2]:
            actions = st.multiselect("Recommended action", [ACTION_RENEWAL, ACTION_INSPECT, ACTION_MONITOR], placeholder="All actions", key="wl_actions")
        with row1[3]:
            status = st.selectbox("Plan status", PLAN_STATUSES, index=PLAN_STATUSES.index(PLAN_FUNDED), key="wl_status",
                                  help="Funded segments fit inside the current length budget.")
        row2 = st.columns([1, 1, 1, 1.2, 1.2], gap="small")
        with row2[0]:
            materials = st.multiselect("Material", sorted(plan["material"].dropna().astype(str).unique()), placeholder="All materials", key="wl_materials")
        with row2[1]:
            zones = st.multiselect("Location", sorted(plan["zone"].dropna().astype(str).unique()), placeholder="All locations", key="wl_zones")
        with row2[2]:
            review_filter = st.selectbox("Review state", REVIEW_STATUSES, index=REVIEW_STATUSES.index(REVIEW_ALL), key="wl_review",
                                         help="Reviewed marks live in this browser session only.")
        with row2[3]:
            ages = pd.to_numeric(plan["age_years"], errors="coerce").dropna()
            age_range = None
            if len(ages) and ages.min() < ages.max():
                low, high = int(ages.min()), int(ages.max())
                age_range = st.slider("Age at decision year (years)", min_value=low, max_value=high, value=(low, high), key="wl_age")
                if age_range == (low, high):
                    age_range = None
        with row2[4]:
            sort = st.selectbox("Sort by", list(SORT_OPTIONS), key="wl_sort", help="Display order only. Selection always follows planning rank.")

        criteria = Criteria(
            search=search,
            bands=bands,
            actions=actions,
            materials=materials,
            zones=zones,
            plan_status=status,
            review_status=review_filter,
            reviewed_ids=reviewed,
            age_range=age_range,
            sort=sort,
        )
        view = filter_worklist(plan, criteria)
        funded_visible = int(view["selected"].sum()) if len(view) else 0
        st.caption(
            f"Showing {len(view):,} of {len(plan):,} segments · {funded_visible:,} of them in the plan · "
            f"{km_text(float(view['length_m'].sum()) if len(view) else 0.0)} shown · decision year {meta['decision_year']}."
        )
        event = None
        if view.empty:
            st.info("No segments match these filters. Clear a filter, choose 'All segments', or raise the budget in the sidebar.")
        else:
            event = st.dataframe(
                styled(register_frame(view)),
                hide_index=True,
                column_config=worklist_columns(plan),
                height=table_height(len(view)),
                on_select="rerun",
                selection_mode="single-row",
                key="wl_table",
            )
        buttons = st.columns([1, 1, 2])
        with buttons[0]:
            st.download_button(
                "Export current view (CSV)",
                data=export_csv(view),
                file_name=f"jagapaip_worklist_view_{meta['decision_year']}.csv",
                mime="text/csv",
                disabled=view.empty,
                help="The rows shown above, in the order shown, with every filter applied.",
                width="stretch",
            )
        with buttons[1]:
            funded = plan.loc[plan["selected"]].sort_values("rank")
            st.download_button(
                "Export funded plan (CSV)",
                data=export_csv(funded),
                file_name=f"jagapaip_funded_plan_{meta['decision_year']}.csv",
                mime="text/csv",
                disabled=funded.empty,
                help="All segments selected at the current budget, in planning order.",
                width="stretch",
            )

    selected_rows = []
    if event is not None and hasattr(event, "selection"):
        selected_rows = list(event.selection.get("rows", []))
    with panel("why"):
        if not selected_rows:
            panel_head("Inspect a selected segment", "Select a row in the register to see its evidence, recommended action, and review controls.")
            st.info("No segment is selected. Click a row above to inspect it.")
            return
        row = view.iloc[int(selected_rows[0])]
        pipe_id = str(row["pipe_id"])
        already = pipe_id in reviewed
        panel_head(f"{pipe_id} · rank {int(row['rank'])} · {row['priority_label']}", row["priority_reason"])
        left, right = st.columns([1, 1.4], gap="medium")
        with left:
            fact_list(
                [
                    ("Location", str(row["location"])),
                    ("Risk score", f"{float(row['predicted_risk']):.3f}"),
                    ("Risk category", str(row["risk_band"])),
                    ("Priority", str(row["priority_label"])),
                    ("Recommended action", str(row["recommended_action"])),
                    ("Evidence", str(row["evidence"])),
                    ("Length", show_text(row["length_m"], 0, " m")),
                    ("Budget decision", str(row["selection_reason"])),
                    ("Review", "Reviewed this session" if already else "Needs review"),
                ]
            )
        with right:
            show_html(f"<p class='jp-panel-sub' style='color:#334155'>{esc(row['explanation'])}</p>")
            actions_row = st.columns(2)
            with actions_row[0]:
                st.button(
                    "View evidence",
                    on_click=go_to,
                    args=("Pipe Evidence",),
                    kwargs={"evidence_pipe": pipe_id},
                    key="wl_open_evidence",
                    width="stretch",
                )
            with actions_row[1]:
                if already:
                    st.button("Mark as needs review", on_click=unmark_reviewed, args=(pipe_id,), key="wl_unreview", width="stretch")
                else:
                    st.button("Mark as reviewed", type="primary", on_click=mark_reviewed, args=(pipe_id,), key="wl_review_mark", width="stretch")
            if reviewed:
                st.button("Clear all review marks", on_click=clear_reviews, key="wl_clear_reviews")
            st.caption("Review marks stay in this session. They do not change rank, budget selection, or any evaluation number.")


def st_chip_scores(plan: pd.DataFrame) -> str:
    from jagapaip.views import chip

    return chip(score_source_label(plan), dot="slate", muted="Scores ")


def reviewed_ids() -> set[str]:
    return {str(item) for item in st.session_state.get("reviewed_pipes", [])}


def mark_reviewed(pipe_id: str) -> None:
    current = list(st.session_state.get("reviewed_pipes", []))
    if pipe_id not in current:
        current.append(pipe_id)
    st.session_state.reviewed_pipes = current


def unmark_reviewed(pipe_id: str) -> None:
    st.session_state.reviewed_pipes = [item for item in st.session_state.get("reviewed_pipes", []) if item != pipe_id]


def clear_reviews() -> None:
    st.session_state.reviewed_pipes = []


# ---------------------------------------------------------------- Proof Mode

def proof_table(plan: pd.DataFrame) -> pd.DataFrame:
    funded = plan.loc[plan["selected"]].sort_values("rank")
    return pd.DataFrame(
        {
            "Rank": funded["rank"],
            "Pipe ID": funded["pipe_id"],
            "Location": funded["zone"],
            "Score": funded["predicted_risk"],
            "Band": funded["risk_band"],
            "Action": funded["recommended_action"],
            "Material": funded["material"],
            "Age": funded["age_years"],
            "Length (m)": funded["length_m"],
            "Prior breaks": funded["historical_breaks"],
            "Installed": funded["install_year"],
        }
    )


def proof_columns(year: int) -> dict:
    return {
        "Rank": st.column_config.NumberColumn("Rank", format="%d", width="small"),
        "Pipe ID": st.column_config.TextColumn("Pipe ID", width="small"),
        "Score": st.column_config.NumberColumn("Score", format="%.3f", width="small", help="Risk score at the evaluation year."),
        "Age": st.column_config.NumberColumn("Age", format="%.0f", width="small"),
        "Length (m)": st.column_config.NumberColumn("Length (m)", format="%.0f", width="small"),
        "Prior breaks": st.column_config.NumberColumn("Prior breaks", format="%.0f", width="small", help=f"Recorded breaks on or before {year}."),
        "Installed": st.column_config.NumberColumn("Installed", format="%d", width="small"),
    }


def pct(value: float | None) -> str | None:
    return None if value is None else f"{100 * value:.1f}"


def contract_proof_table(plan: pd.DataFrame, features: pd.DataFrame | None) -> pd.DataFrame:
    """Selected pipes for one contract plan. Outcomes are deliberately not included."""
    chosen = plan.loc[plan["selected"], ["rank", "segment_id", "risk_percentile", "length_m"]
                      + [c for c in ("confidence_label",) if c in plan.columns]].copy()
    table = pd.DataFrame(
        {
            "Rank": chosen["rank"],
            "Pipe ID": chosen["segment_id"],
            "Risk percentile": chosen["risk_percentile"],
            "Confidence": chosen["confidence_label"] if "confidence_label" in chosen else None,
            "Length (m)": chosen["length_m"],
        }
    )
    if features is not None and not features.empty:
        facts = features.drop_duplicates("pipe_id").set_index("pipe_id")
        for column, label in (("material", "Material"), ("age_years", "Age"), ("historical_breaks", "Prior breaks")):
            if column in facts.columns:
                table[label] = table["Pipe ID"].map(facts[column])
    return table


def page_proof_contract(dataset: dict) -> None:
    """Proof Mode on Contract B rankings with every number read from metrics.json."""
    meta, metrics, contract_b = dataset["meta"], dataset["metrics"], dataset["contract_b"]
    champion_name = meta.get("champion_method") or "champion"
    page_header(
        "Proof Mode",
        "Pick a past year, fix both plans under the same network-length budget, then reveal what broke that year.",
        standard_chips(meta),
    )
    if meta.get("metrics_synthetic"):
        notice(
            "SYNTHETIC METRICS — NOT RESULTS",
            ["metrics.json is flagged is_synthetic. These numbers are schema examples and must not be presented."],
            warn=True,
        )
    notice(
        "What this test uses",
        [
            f"JagaPaip plan: the measured champion ({champion_name}) from fold_predictions. Each year was scored using only earlier years.",
            "Baseline: oldest-first from the same file, with the same eligible pipes and the same length budget.",
            "Every count and rate below is copied from metrics.json (the team's walk-forward evaluation). The app does not compute them.",
            "City of Kitchener open data — a method demonstrator. It does not establish effectiveness for Malaysian utilities.",
        ],
    )

    years = contract_years(metrics)
    budgets = contract_budgets(metrics)
    if not years or not budgets:
        notice("metrics.json has no test years or budgets", ["Proof Mode cannot run until metrics.json lists them."], warn=True)
        return
    with panel("proof_setup"):
        step_title(1, "Choose the test year and budget", "Only years and budgets evaluated in metrics.json are offered.")
        controls = st.columns([1, 1.3, 1.4], gap="medium")
        with controls[0]:
            if st.session_state.get("cproof_year") not in years:
                st.session_state.cproof_year = max(years)
            year = int(st.selectbox("Test year", years, key="cproof_year",
                                    help="Rankings use only information available before 1 January of this year."))
        with controls[1]:
            if st.session_state.get("cproof_budget") not in budgets:
                st.session_state.cproof_budget = 0.05 if 0.05 in budgets else budgets[0]
            budget = float(st.select_slider("Length budget (share of network)", options=budgets, key="cproof_budget",
                                            format_func=lambda b: f"{b:.0%}", help="The same share of network length for both plans."))
        plans = contract_plans(contract_b, year, budget)
        champion, oldest = plans[CONTRACT_CHAMPION], plans[CONTRACT_OLDEST]
        budget_m = float(champion["budget_length_m"].iloc[0]) if len(champion) else 0.0
        network_m = float(champion["length_m"].sum())
        with controls[2]:
            fact_list(
                [
                    ("Eligible population", f"{len(champion):,} segments · {km_text(network_m)}"),
                    ("Budget for both plans", f"{budget:.0%} of network = {km_text(budget_m)}"),
                    ("Held-back outcome", f"Recorded breaks during {year}"),
                ]
            )

    signature = ("contract", year, budget)
    if st.session_state.get("proof_sig") != signature:
        st.session_state.proof_sig = signature
        st.session_state.proof_revealed = False

    features = None
    panel_frame = dataset.get("panel")
    if panel_frame is not None and "year" in panel_frame.columns:
        features = panel_frame.loc[pd.to_numeric(panel_frame["year"], errors="coerce") == year]
    with panel("proof_plans"):
        step_title(2, "Compare the two plans", "Both lists are fixed now, before any outcome is read. Outcomes are not in these tables.")
        if "proof_show_selections" not in st.session_state:
            st.session_state.proof_show_selections = True
        show_sel, hide_sel = st.columns([1, 1])
        with show_sel:
            st.button("Show selected segments", on_click=show_selections, key="proof_show_sel", disabled=bool(st.session_state.proof_show_selections), width="stretch")
        with hide_sel:
            st.button("Hide selected segments", on_click=hide_selections, key="proof_hide_sel", disabled=not bool(st.session_state.proof_show_selections), width="stretch")
        left, right = st.columns(2, gap="medium")
        for column, plan, title, dot, sub in (
            (left, champion, "JagaPaip plan", "teal", f"Measured champion ({champion_name}), highest risk percentile first."),
            (right, oldest, "Oldest-first baseline", "slate", "Same eligible pipes and budget, oldest pipe first."),
        ):
            with column:
                chosen = plan.loc[plan["selected"]]
                show_html(
                    f"<p class='jp-panel-title' style='font-size:0.98rem'><span class='dot {dot}'></span>&nbsp; {esc(title)} "
                    f"<span class='jp-panel-meta'>· {len(chosen)} segments · {km_text(float(chosen['length_m'].sum()))}</span></p>"
                )
                st.caption(sub)
                if not st.session_state.proof_show_selections:
                    st.info("Selections are hidden. Click Show selected segments to inspect which pipes each method funded.")
                elif chosen.empty:
                    st.info("No segment fits this budget.")
                else:
                    st.dataframe(contract_proof_table(plan, features), hide_index=True, height=table_height(len(chosen), 380),
                                 column_config={"Risk percentile": st.column_config.NumberColumn(format="%.3f")})
        st.caption(
            "Both lists stop at the first pipe that would overflow the budget, the rule used by metrics.json and the decision engine."
        )

    with panel("proof_reveal"):
        step_title(3, "Reveal actual outcomes", f"Pipes with at least one recorded break during {year}, on the same eligible pipes.")
        revealed = bool(st.session_state.get("proof_revealed", False))
        if not revealed:
            pre = plan_mismatches(plans, metrics, year, budget, revealed=False)
            if pre:
                notice("Plans do not match metrics.json — do not present", pre, warn=True)
            fact_list(
                [
                    ("Outcome", f"Recorded breaks during {year}"),
                    ("Budget for the comparison", f"{budget:.0%} of network = {km_text(budget_m)}"),
                    ("Numbers source", "metrics.json (copied, not recomputed)"),
                ]
            )
            st.caption("Outcomes are hidden and have not been read for this comparison.")
            st.button("Reveal Actual Outcomes", type="primary", on_click=reveal_outcomes, key="proof_reveal_btn")
            return

        ours = metrics_cell(metrics, year, budget, CONTRACT_CHAMPION) or {}
        base = metrics_cell(metrics, year, budget, CONTRACT_OLDEST) or {}
        problems = plan_mismatches(plans, metrics, year, budget, revealed=True)
        if problems:
            notice("Mismatch with metrics.json — do not present", problems, warn=True)
        total = metrics.get("by_year", {}).get(str(year), {}).get("summary", {}).get("total_breaks")
        interval = year_interval(metrics, year, budget)
        kpi_grid(
            [
                {"label": f"JagaPaip capture at {budget:.0%}", "value": pct(ours.get("capture")), "unit": "%", "fallback": "Unavailable",
                 "note": f"{ours.get('breaks_captured', '—')} of {total if total is not None else '—'} broken pipes, in {ours.get('selected_segments', '—')} selected.", "dot": "teal"},
                {"label": f"Oldest-first capture at {budget:.0%}", "value": pct(base.get("capture")), "unit": "%", "fallback": "Unavailable",
                 "note": f"{base.get('breaks_captured', '—')} of {total if total is not None else '—'} broken pipes, in {base.get('selected_segments', '—')} selected.", "dot": "slate"},
                {"label": "Difference, 95% interval", "value": None if not interval else f"{100 * interval[0]:.0f} to {100 * interval[1]:.0f}",
                 "unit": "pts", "fallback": "Unavailable", "note": f"JagaPaip minus oldest-first capture in {year} (bootstrap).", "dot": "amber"},
                {"label": f"Broken pipes in {year}", "value": None if total is None else f"{total:,}",
                 "note": "Eligible pipes with at least one recorded break.", "dot": "slate"},
            ]
        )

        def row(label: str, key: str, fmt) -> dict:
            return {"Metric": label, "JagaPaip": fmt(ours.get(key)), "Oldest-first": fmt(base.get(key))}

        def num(value):
            return "—" if value is None else f"{value:,}"

        def rate(value):
            return "Unavailable" if value is None else f"{100 * value:.1f}%"

        left, right = st.columns([1, 1.2], gap="medium")
        with left:
            st.dataframe(
                pd.DataFrame(
                    [
                        row("Segments selected", "selected_segments", num),
                        row("Length selected (km)", "selected_length_m", lambda v: "—" if v is None else f"{v / 1000:.2f}"),
                        row("Broken pipes in the plan", "breaks_captured", num),
                        row("Capture (share of all broken pipes)", "capture", rate),
                        row("Precision (broken ÷ selected)", "precision", rate),
                        row("Selected without a recorded break", "observed_non_events", num),
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
            st.caption(f"Test year {year}, budget {budget:.0%} of network length. Values copied from metrics.json.")
        with right:
            st.markdown(f"**All test years ({', '.join(str(y) for y in years)}), budget {budget:.0%}**")
            st.dataframe(across_years(metrics, budget), hide_index=True, width="stretch",
                         column_config={"Capture (mean of test years)": st.column_config.NumberColumn(format="percent")})
        fact_list(
            [
                ("Plan integrity", "Plans unchanged by the reveal · lists reproduce metrics.json" if not problems
                 else "Mismatch — investigate before presenting"),
                ("Source", f"{meta['files'].get('metrics') or 'metrics.json'} · generated {metrics.get('generated_at', '—')}"),
                ("Data snapshot", str(metrics.get("data_snapshot", "—"))),
            ]
        )
        with st.expander("Metric definitions, assumptions, and limitations"):
            st.markdown(
                f"""
                - **Capture** = pipes with at least one recorded break during {year} that are in the plan ÷ all such pipes in the eligible population.
                - **Same budget**: both plans get {budget:.0%} of the eligible network length and stop at the first pipe that would overflow it.
                - **A selected pipe without a recorded break** is an observed non-event, not proof that inspecting it was unnecessary.
                - **This measures targeting quality**, not breaks prevented or money saved.
                - **Limitations**: see `metrics.json → limitations` and the model card (`docs/model-card.md`). Kitchener open data is a
                  method demonstrator and does not establish effectiveness for Malaysian utilities.
                """
            )
        st.button("Hide outcomes again", on_click=hide_outcomes, key="proof_hide_btn")


def page_proof(dataset: dict) -> None:
    meta = dataset["meta"]
    if meta.get("contract_mode"):
        page_proof_contract(dataset)
        return
    demo = meta["mode"] == "demo"
    page_header(
        "Proof Mode",
        "Rewind to a past year, build two plans under the same length budget, then reveal what actually happened next.",
        standard_chips(meta),
    )
    years = available_evaluation_years(dataset, PROOF_HORIZON_YEARS)
    if not years:
        notice(
            "Outcome comparison is unavailable for this data",
            [
                "Proof Mode needs breaks dated by year, so a window after the decision year can be held back.",
                f"It also needs at least {PROOF_HORIZON_YEARS} years of ledger after the decision year. Neither condition is met.",
                "This is a gap in the file, not evidence of zero breaks. The operational pages still work.",
            ],
            warn=True,
        )
        st.button("Reveal Actual Outcomes", disabled=True, help="Unavailable: no dated outcome history.")
        return

    has_predictions = dataset["predictions"] is not None
    notice(
        "What this test uses",
        [
            "Outcome labels: " + (
                "synthetic break ledger generated by the demo — not real utility data."
                if demo
                else (
                    "dated completed main-break records from the Member 1 Kitchener ledger (breaks_clean)."
                    if meta.get("demonstrator")
                    else "dated breaks from the loaded break ledger."
                )
            ),
            "Historical predictions: " + (
                "fold_predictions supplied; scores for the chosen year are used where present."
                if has_predictions
                else "none supplied. The JagaPaip plan uses the screening heuristic recomputed from facts at the decision year. This is not a trained-model evaluation."
            ),
            "Neither plan can see breaks after the evaluation year. Outcomes are read only after you click Reveal.",
        ],
        warn=demo or not has_predictions,
    )

    with panel("proof_setup"):
        step_title(1, "Choose the historical decision point", "Only years with a complete outcome window in the ledger are offered.")
        controls = st.columns([1, 1.3, 1.4], gap="medium")
        with controls[0]:
            default_year = 2016 if 2016 in years else years[len(years) // 2]
            if "proof_year" not in st.session_state or st.session_state.proof_year not in years:
                st.session_state.proof_year = default_year
            year = int(st.selectbox("Evaluation year", years, key="proof_year", help="Plans may use only breaks dated in this year or earlier."))
        features = features_for_year(dataset, year)
        length_km = float(features["length_m"].sum()) / 1000 if len(features) else 0.0
        ceiling = slider_ceiling(length_km)
        with controls[1]:
            if "proof_budget_km" not in st.session_state:
                default = min(ceiling, 5.0) if length_km >= 50 else min(ceiling, max(0.2, length_km * 0.15))
                st.session_state.proof_budget_km = snap(default)
            if st.session_state.proof_budget_km > ceiling:
                st.session_state.proof_budget_km = ceiling
            proof_budget_km = st.slider("Length budget (km)", min_value=0.0, max_value=ceiling, step=0.1, key="proof_budget_km",
                                        help="The same length budget is given to both plans.")
        with controls[2]:
            fact_list(
                [
                    ("Eligible population", f"{len(features):,} segments · {length_km:.2f} km"),
                    ("Held-back outcome window", f"{year + 1} to {year + PROOF_HORIZON_YEARS}"),
                    ("Scores", score_source_label(build_plan(features, 0.0))),
                ]
            )

    signature = (year, round(float(proof_budget_km), 2), PROOF_HORIZON_YEARS)
    if st.session_state.get("proof_sig") != signature:
        st.session_state.proof_sig = signature
        st.session_state.proof_revealed = False

    budget_m = float(proof_budget_km) * 1000
    jagapaip = build_plan(features, budget_m, STRATEGY_JAGAPAIP)
    baseline = build_plan(features, budget_m, STRATEGY_OLDEST)
    comparison = compare_plans(jagapaip, baseline, budget_m)
    ours_comp = comparison["jagapaip"]
    base_comp = comparison["oldest_first"]
    with panel("proof_plans"):
        step_title(2, "Compare the two plans", "Both are fixed now, before any outcome is read. Future breaks are not in these tables.")
        if "proof_show_selections" not in st.session_state:
            st.session_state.proof_show_selections = True
        show_sel, hide_sel = st.columns([1, 1])
        with show_sel:
            st.button("Show selected segments", on_click=show_selections, key="proof_show_sel", disabled=bool(st.session_state.proof_show_selections), width="stretch")
        with hide_sel:
            st.button("Hide selected segments", on_click=hide_selections, key="proof_hide_sel", disabled=not bool(st.session_state.proof_show_selections), width="stretch")
        left, right = st.columns(2, gap="medium")
        for column, plan, title, dot, sub in (
            (left, jagapaip, "JagaPaip plan", "teal", "Ordered by risk score, then funded while remaining length still fits."),
            (right, baseline, "Oldest-first baseline", "slate", "Same length budget, ordered by install year, oldest first."),
        ):
            with column:
                chosen = plan.loc[plan["selected"]]
                show_html(
                    f"<p class='jp-panel-title' style='font-size:0.98rem'><span class='dot {dot}'></span>&nbsp; {esc(title)} "
                    f"<span class='jp-panel-meta'>· {len(chosen)} segments · {km_text(float(chosen['length_m'].sum()))}</span></p>"
                )
                st.caption(sub)
                if not st.session_state.proof_show_selections:
                    st.info("Selections are hidden. Click Show selected segments to inspect which pipes each method funded.")
                elif chosen.empty:
                    st.info("No segment fits this budget. Raise the length budget.")
                else:
                    st.dataframe(styled(proof_table(plan)), hide_index=True, column_config=proof_columns(year), height=table_height(len(chosen), 380))

        notice(
            "Plan composition — not a measured improvement",
            [
                "The figures below describe the two plans using the same scores and the same length budget.",
                "Score mass uses the scores that ranked JagaPaip, so JagaPaip will usually look better on that number by construction.",
                "These are not leak reductions, cost savings, or field-validated results.",
            ],
            warn=True,
        )
        kpi_grid(
            [
                {
                    "label": "JagaPaip length used",
                    "value": f"{ours_comp['length_m'] / 1000:.2f}",
                    "unit": "km",
                    "note": f"of {km_text(budget_m)} budget · {ours_comp['segments']} segments.",
                    "dot": "teal",
                },
                {
                    "label": "Oldest-first length used",
                    "value": f"{base_comp['length_m'] / 1000:.2f}",
                    "unit": "km",
                    "note": f"of {km_text(budget_m)} budget · {base_comp['segments']} segments.",
                    "dot": "slate",
                },
                {
                    "label": "High-risk covered",
                    "value": f"{ours_comp['high_risk_selected']} vs {base_comp['high_risk_selected']}",
                    "note": f"JagaPaip vs oldest-first, of {ours_comp['high_risk_in_network']} high-risk segments.",
                    "dot": "amber",
                },
                {
                    "label": "Score mass in plan",
                    "value": f"{ours_comp['score_sum']:.2f} vs {base_comp['score_sum']:.2f}",
                    "note": "Sum of the same ranking scores. Not a measured risk reduction.",
                    "dot": "slate",
                },
            ]
        )
        overlap_left, overlap_right = st.columns([1.15, 1], gap="medium")
        with overlap_left:
            show_chart(charts.selection_overlap_chart(comparison))
            st.caption(
                f"{len(comparison['overlap_ids'])} segments appear in both plans · "
                f"{len(comparison['only_jagapaip'])} only in JagaPaip · "
                f"{len(comparison['only_oldest'])} only in oldest-first."
            )
        with overlap_right:
            diffs = difference_rows(jagapaip, baseline, comparison)
            if diffs.empty:
                st.info("Both methods selected the same segments at this budget.")
            else:
                st.dataframe(diffs, hide_index=True, height=table_height(len(diffs), 320), width="stretch")
                st.caption("Why the lists differ: JagaPaip spends length on higher scores; oldest-first spends it on earlier install years.")

    with panel("proof_reveal"):
        step_title(3, "Reveal actual outcomes", f"Recorded breaks from {year + 1} to {year + PROOF_HORIZON_YEARS} on the eligible population.")
        revealed = bool(st.session_state.get("proof_revealed", False))
        if not revealed:
            fact_list(
                [
                    ("Evaluation period", f"{year + 1} to {year + PROOF_HORIZON_YEARS} ({PROOF_HORIZON_YEARS} years after the decision)"),
                    ("Eligible population", f"Segments in service at the end of {year} with a positive length"),
                    ("Budget for the comparison", km_text(budget_m)),
                    (f"Capture@{CAPTURE_FRACTION:.0%} budget", f"{CAPTURE_FRACTION:.0%} of eligible length = {length_km * CAPTURE_FRACTION:.2f} km"),
                ]
            )
            st.caption("Outcomes are hidden and have not been read for this comparison.")
            st.button("Reveal Actual Outcomes", type="primary", on_click=reveal_outcomes, key="proof_reveal_btn")
            return

        with st.spinner("Reading the held-out outcome window…"):
            result = run_backtest(features, dataset["breaks"], year, budget_m)
        integrity = (
            result["plans"]["budget"][STRATEGY_JAGAPAIP].loc[lambda f: f["selected"], "pipe_id"].tolist()
            == jagapaip.loc[jagapaip["selected"], "pipe_id"].tolist()
            and result["plans"]["budget"][STRATEGY_OLDEST].loc[lambda f: f["selected"], "pipe_id"].tolist()
            == baseline.loc[baseline["selected"], "pipe_id"].tolist()
        )
        if demo:
            notice(
                "DEMO SIMULATION — NOT A VALIDATED RESULT",
                [
                    "These numbers check the mechanics on a synthetic ledger. They are not model accuracy, savings, or evidence for any utility.",
                    "The demo generator used age and material to simulate breaks, and the heuristic uses the same inputs, so agreement is expected by construction.",
                ],
                warn=True,
            )
        elif meta.get("demonstrator"):
            notice(
                "KITCHENER HOLD-OUT — NOT A MALAYSIAN OR MODEL RESULT",
                [
                    "These capture rates use completed main-break records on the current Kitchener inventory. They are not model accuracy, savings, or leak prevention.",
                    "No fold_predictions file was supplied. The JagaPaip side is the screening heuristic. This does not establish effectiveness for Malaysian utilities.",
                ],
                warn=True,
            )
        render_backtest(result, integrity)
        st.button("Hide outcomes again", on_click=hide_outcomes, key="proof_hide_btn")


def reveal_outcomes() -> None:
    st.session_state.proof_revealed = True


def hide_outcomes() -> None:
    st.session_state.proof_revealed = False


def show_selections() -> None:
    st.session_state.proof_show_selections = True


def hide_selections() -> None:
    st.session_state.proof_show_selections = False


def reveal_simulation() -> None:
    st.session_state.eval_sim_revealed = True


def render_backtest(result: dict, integrity: bool) -> None:
    ours_cap = result["at_capture"][STRATEGY_JAGAPAIP]
    base_cap = result["at_capture"][STRATEGY_OLDEST]
    no_breaks = result["eligible_breaks"] == 0
    fraction = f"{result['capture_fraction']:.0%}"
    kpi_grid(
        [
            {"label": f"JagaPaip Capture@{fraction}", "value": pct(ours_cap["capture_rate"]), "unit": "%",
             "fallback": "Unavailable", "note": f"{ours_cap['captured_breaks']} of {result['eligible_breaks']} window breaks.", "dot": "teal"},
            {"label": f"Oldest-first Capture@{fraction}", "value": pct(base_cap["capture_rate"]), "unit": "%",
             "fallback": "Unavailable", "note": f"{base_cap['captured_breaks']} of {result['eligible_breaks']} window breaks.", "dot": "slate"},
            {"label": f"Ratio at {fraction}", "value": None if result["lift_at_capture"] is None else f"{result['lift_at_capture']:.2f}",
             "unit": "×", "fallback": "Unavailable", "note": "JagaPaip capture ÷ oldest-first capture. Unavailable if the baseline captured none.", "dot": "slate"},
            {"label": "Breaks in window", "value": f"{result['eligible_breaks']:,}",
             "note": f"{result['segments_with_break']} eligible segments broke at least once.", "dot": "amber"},
        ]
    )
    if no_breaks:
        notice("No breaks were recorded in this window", ["Capture rates are undefined when the window has no recorded breaks. Choose another year."], warn=True)

    def row(metric: str, key: str, fmt) -> dict:
        return {
            "Metric": metric,
            "JagaPaip @ your budget": fmt(result["at_budget"][STRATEGY_JAGAPAIP][key]),
            "Oldest-first @ your budget": fmt(result["at_budget"][STRATEGY_OLDEST][key]),
            f"JagaPaip @ {fraction}": fmt(result["at_capture"][STRATEGY_JAGAPAIP][key]),
            f"Oldest-first @ {fraction}": fmt(result["at_capture"][STRATEGY_OLDEST][key]),
        }

    def num(value):
        return "—" if value is None else f"{value:,}"

    def rate(value):
        return "Unavailable" if value is None else f"{100 * value:.1f}%"

    def per_km(value):
        return "Unavailable" if value is None else f"{value:.2f}"

    table = pd.DataFrame(
        [
            row("Segments selected", "segments", num),
            row("Length selected (km)", "length_m", lambda v: f"{v / 1000:.2f}"),
            row("Window breaks on selected segments", "captured_breaks", num),
            row("Capture rate (share of all window breaks)", "capture_rate", rate),
            row("Selected segments with ≥1 break", "segments_hit", num),
            row("Breaks per km selected", "breaks_per_km", per_km),
        ]
    )
    left, right = st.columns([3, 2], gap="medium")
    with left:
        st.dataframe(table, hide_index=True, width="stretch")
        st.caption(
            f"Your budget: {km_text(result['budget_m'])}. Capture@{fraction} budget: {km_text(result['capture_budget_m'])} "
            f"({fraction} of the {km_text(result['eligible_length_m'])} eligible network)."
        )
    with right:
        show_chart(charts.capture_rate_chart(result))
    fact_list(
        [
            ("Plan integrity", "Plans unchanged by the reveal" if integrity else "Mismatch — investigate before presenting"),
            ("Evaluation period", f"{result['window'][0]} to {result['window'][1]}"),
            ("Eligible population", f"{result['eligible_segments']:,} segments · {km_text(result['eligible_length_m'])}"),
            ("Breaks on ineligible pipes (excluded)", f"{result['excluded_breaks']:,}"),
        ]
    )
    with st.expander("Metric definitions, assumptions, and limitations"):
        st.markdown(
            f"""
            - **Capture rate** = recorded breaks in the outcome window on the selected segments ÷ all recorded breaks in the window on the eligible population.
            - **Capture@{fraction}** = capture rate when the length budget is {fraction} of the eligible network length, for both plans.
            - **Ratio** = JagaPaip capture ÷ oldest-first capture at the same budget.
            - **Eligible population** = segments in service at the end of {result['year']} with a positive length. Breaks on segments installed later are excluded.
            - **Assumptions:** recorded breaks stand in for failures; every selected segment is treated as fully intervened; repairs during the window are not modelled.
            - **Limitations:** one historical year is a single test, not a validated performance estimate. Under-reported breaks bias every plan.
              City of Kitchener data, if used, is a method demonstrator and does not establish effectiveness for Malaysian utilities.
            """
        )


# ---------------------------------------------------------------- Evaluation & Data Quality

ARTIFACTS = {
    "pipe_year": ("pipe_year.parquet", "Pipe attributes and dated breaks"),
    "fold_predictions": ("fold_predictions.parquet", "Model scores used for ranking"),
    "metrics": ("metrics.json", "Evaluation results, shown as reported"),
    "ranked_worklists": ("ranked_worklists.parquet", "Supplied ranking, preview only"),
}

STATUS_TONE = {PASS: "low", WARN: "moderate", INFO: "slate", MISSING: "high"}
CLASS_TONE = {
    "Synthetic": "moderate",
    "Observed": "teal",
    "Model": "teal",
    "Screening": "slate",
    "Measured": "teal",
    "Missing": "high",
    "Simulated": "moderate",
    "Computed": "slate",
    "Unavailable": "high",
}


def flatten_metrics(value, prefix: str = "") -> list[dict]:
    import json

    rows: list[dict] = []
    if isinstance(value, dict):
        for key, item in value.items():
            rows.extend(flatten_metrics(item, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        rows.append({"Field": prefix or "value", "Reported value": json.dumps(value, ensure_ascii=True)})
    else:
        rows.append({"Field": prefix or "value", "Reported value": value})
    return rows


def html_table(headers: list[str], rows: list[list[str]]) -> None:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    show_html(f"<div class='jp-table-wrap'><table class='jp-table'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def page_evaluation(dataset: dict, plan: pd.DataFrame) -> None:
    meta = dataset["meta"]
    page_header(
        "Evaluation & Data Quality",
        "What the loaded files contain, where every number comes from, and what this dashboard will not claim.",
        standard_chips(meta),
    )
    found = sum(1 for key in ARTIFACTS if meta["files"].get(key))
    pipes, metrics = dataset["pipes"], dataset["metrics"]
    checks = run_checks(dataset)
    warnings = sum(1 for c in checks if c["Status"] in (WARN, MISSING))
    if metrics is None:
        notice(
            "No genuine measured results are loaded",
            [
                "metrics.json is not in the project. JagaPaip will not invent accuracy, savings, leak prevention, or ROI.",
                "Proof Mode can run a transparent comparison on the loaded ledger. On demo data that comparison is a simulation, not a validation.",
            ],
            warn=True,
        )
    elif meta["mode"] == "demo":
        notice(
            "Measured file present — demo network is still synthetic",
            [
                "metrics.json is shown as reported. It is not a score for the synthetic demo network on the other pages.",
            ],
            warn=True,
        )
    kpi_grid(
        [
            {"label": "Team artifacts found", "value": f"{found}", "unit": f"of {len(ARTIFACTS)}", "note": "Files detected in the project folders.", "dot": "teal" if found else "amber"},
            {"label": "Segments loaded", "value": f"{len(pipes):,}", "note": "Synthetic demo network." if meta["mode"] == "demo" else "From pipe_year.", "dot": "slate"},
            {"label": "Quality checks flagged", "value": f"{warnings}", "unit": f"of {len(checks)}", "note": "Warnings plus missing inputs.", "dot": "amber" if warnings else "green"},
            {"label": "Model evaluation", "value": None if metrics is None else "Reported", "fallback": "Not yet evaluated",
             "note": "No metrics.json is loaded." if metrics is None else "Values copied from metrics.json.", "dot": "amber" if metrics is None else "teal"},
        ]
    )

    with panel("provenance"):
        panel_head("Where each number comes from", "Every quantity on this dashboard falls into exactly one of these classes.")
        rows = []
        for item in provenance(dataset, score_source_label(plan)):
            label = item["Classification"]
            tone = next((tone for key, tone in CLASS_TONE.items() if label.startswith(key)), "slate")
            rows.append([f"<strong>{esc(item['Element'])}</strong>", pill(label, tone), f"<span class='sub'>{esc(item['Source'] or '—')}</span>"])
        html_table(["Element", "Classification", "Source"], rows)

    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        with panel("quality"):
            panel_head("Data-quality checks", f"Run on the loaded tables at decision year {meta['decision_year']}. Counts only; nothing is auto-corrected.")
            rows = []
            for check in checks:
                count = "—" if check["Count"] is None else f"{check['Count']:,}"
                rows.append(
                    [
                        esc(check["Check"]),
                        pill(check["Status"], STATUS_TONE.get(check["Status"], "slate")),
                        count,
                        f"<span class='sub'>{esc(check['Detail'])}</span>",
                    ]
                )
            html_table(["Check", "Status", "Count", "Detail"], rows)
    with right:
        with panel("artifacts"):
            panel_head("Artifact checklist", "Drop files into the data folder and refresh the page.")
            rows = []
            for key, (filename, role) in ARTIFACTS.items():
                path = meta["files"].get(key, "")
                rows.append([f"<strong>{esc(filename)}</strong><div class='sub'>{esc(role)}</div>",
                             pill("Found", "teal") if path else pill("Not in project", "slate")])
            html_table(["File", "Status"], rows)
            if not found:
                st.caption("No team artifacts were found, so every page runs on the labelled synthetic demo network.")

    with panel("metrics"):
        panel_head("Reported evaluation metrics", "Source: metrics.json. JagaPaip copies these values and does not recalculate them.")
        if metrics is None:
            notice(
                "Not yet evaluated",
                [
                    "metrics.json is not in the project folder or could not be read.",
                    "JagaPaip will not estimate accuracy, financial savings, or ROI to fill that gap. Proof Mode results are a separate, single-year check.",
                ],
                warn=True,
            )
        else:
            if meta["mode"] == "demo":
                st.warning("The network on the other pages is synthetic. Do not treat this file as a score for that demo network.")
            st.dataframe(pd.DataFrame(flatten_metrics(metrics)), hide_index=True)
            with st.expander("Original metrics.json"):
                st.json(metrics)

    worklists = dataset["worklists"]
    if worklists is not None:
        with panel("worklists"):
            panel_head("Supplied ranked worklist", f"{len(worklists):,} rows from ranked_worklists. Preview only; the live plan is recalculated.")
            st.dataframe(worklists.head(20), hide_index=True, height=360)

    if meta["warnings"]:
        notice("File notes", list(meta["warnings"]), warn=True)

    with panel("validation_needs"):
        panel_head(
            "What field validation would still require",
            "A working dashboard is not evidence that the method is effective for a utility.",
        )
        need_rows = [
            [f"<strong>{esc(item['Requirement'])}</strong>", f"<span class='sub'>{esc(item['Why it is required'])}</span>"]
            for item in field_validation_needs()
        ]
        html_table(["Requirement", "Why it is required"], need_rows)

    with panel("simulated"):
        panel_head(
            "Transparent simulated evaluation",
            "Optional. Uses the same hold-out method as Proof Mode. It is not a substitute for metrics.json.",
        )
        years = [] if meta.get("contract_mode") else available_evaluation_years(dataset, PROOF_HORIZON_YEARS)
        if meta.get("contract_mode"):
            st.info(
                "Measured results are loaded (metrics.json and fold_predictions), so the screening-heuristic simulation is "
                "turned off: it would put unvalidated numbers next to measured ones. Proof Mode shows the measured comparison."
            )
        elif not years:
            st.info("No complete outcome window is available, so a simulated evaluation cannot be generated from this file.")
        else:
            sim_year = years[-1]
            features = features_for_year(dataset, sim_year)
            length_m = float(features["length_m"].sum()) if len(features) else 0.0
            sim_budget = length_m * CAPTURE_FRACTION
            st.caption(
                f"Eligible year {sim_year}, window {sim_year + 1}–{sim_year + PROOF_HORIZON_YEARS}, "
                f"budget {km_text(sim_budget)} ({CAPTURE_FRACTION:.0%} of eligible length)."
            )
            st.button("Generate simulated evaluation", on_click=reveal_simulation, key="eval_run_sim")
            if st.session_state.get("eval_sim_revealed"):
                if meta["mode"] == "demo":
                    notice(
                        "DEMO SIMULATION — NOT A VALIDATED RESULT",
                        [
                            "The demo generator used age and material to simulate breaks, and the heuristic uses the same inputs.",
                            "Agreement is expected by construction. This is not model accuracy or a utility finding.",
                        ],
                        warn=True,
                    )
                elif meta.get("demonstrator"):
                    notice(
                        "KITCHENER HOLD-OUT — NOT A VALIDATED MODEL RESULT",
                        [
                            "This uses the Member 1 break ledger and the screening heuristic. It is not Member 2 model performance and not Malaysian evidence.",
                        ],
                        warn=True,
                    )
                with st.spinner("Computing the hold-out comparison…"):
                    result = run_backtest(features, dataset["breaks"], sim_year, sim_budget)
                render_backtest(result, True)
            else:
                st.info("The simulated comparison stays hidden until you generate it. That keeps Proof Mode’s hide-until-reveal behaviour intact.")

    left, right = st.columns(2, gap="medium")
    with left:
        with panel("definitions"):
            panel_head("Metric definitions")
            contract_mode = bool(meta.get("contract_mode"))
            action_definition = (
                "From the decision engine (Contract C, ranked_worklists). Shown as Awaiting decision engine until that file is loaded."
                if contract_mode
                else "Renewal Review at or above 0.70, Inspect at or above 0.45, otherwise Monitor."
            )
            capture_definition = (
                f"Share of pipes with at least one recorded break during the test year that fall inside a plan using "
                f"{CAPTURE_FRACTION:.0%} of network length. Copied from metrics.json."
                if contract_mode
                else f"Share of outcome-window breaks on segments selected with a budget of {CAPTURE_FRACTION:.0%} of network length."
            )
            window_definition = (
                "Breaks recorded during the test year; rankings use only information from before 1 January of that year."
                if contract_mode
                else "Breaks after the evaluation year. Shown only after reveal, and never used to rank."
            )
            st.markdown(
                f"""
                - **Risk score.** The number used to order the JagaPaip queue. With Contract B it is the measured champion's within-year risk percentile; with no prediction file, it is a screening heuristic, not a probability.
                - **Recommended action.** {action_definition}
                - **Network-length budget.** Kilometres of pipe that may be selected, because monetary cost is absent.
                - **Capture@{CAPTURE_FRACTION:.0%}.** {capture_definition}
                - **Outcome window.** {window_definition}
                - **Oldest-first.** The same length budget, given to the oldest pipes first.
                """
            )
    with right:
        with panel("claims"):
            panel_head("What is not claimed")
            st.markdown(
                """
                - No accuracy, savings, or ROI is calculated unless that number is already inside metrics.json.
                - Proof Mode on demo data checks the mechanics only; it is not a validated finding.
                - City of Kitchener data, if used, is a method demonstrator and does not establish effectiveness for Malaysian utilities.
                - A Malaysian pilot needs pipe, break, and cost records from the local utility, plus a fresh evaluation design.
                """
            )
