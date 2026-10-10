"""Plotly charts for the command-centre layout.

Titles live in the surrounding panel header, so figures carry axes and
tooltips only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from jagapaip.schema import (
    ACTION_INSPECT,
    ACTION_MONITOR,
    ACTION_RENEWAL,
    BAND_HIGH,
    BAND_LOW,
    BAND_MODERATE,
    INSPECT_THRESHOLD,
    RENEWAL_THRESHOLD,
)

TEAL = "#14B8A6"
TEAL_DEEP = "#0D9488"
NAVY = "#14283F"
RED = "#DC2626"
AMBER = "#F59E0B"
GREEN = "#10B981"
SLATE = "#CBD5E1"
INK = "#172B3A"
MUTED = "#64748B"
GRID = "#EEF2F6"

BAND_COLORS = {
    BAND_HIGH: RED,
    BAND_MODERATE: AMBER,
    BAND_LOW: GREEN,
}
ACTION_COLORS = {
    ACTION_RENEWAL: RED,
    ACTION_INSPECT: AMBER,
    ACTION_MONITOR: TEAL_DEEP,
}


def _layout(fig: go.Figure, height: int = 300) -> go.Figure:
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Segoe UI, Inter, sans-serif", "color": INK, "size": 13},
        margin={"l": 64, "r": 16, "t": 16, "b": 52},
        height=height,
        showlegend=False,
        bargap=0.35,
        hoverlabel={"bgcolor": "#FFFFFF", "bordercolor": "#E2E8F0", "font": {"color": INK, "size": 13}},
    )
    fig.update_xaxes(showgrid=False, linecolor="#E2E8F0", automargin=True, tickfont={"size": 12, "color": MUTED}, title_font={"size": 12, "color": MUTED}, title_standoff=10)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, automargin=True, tickfont={"size": 12, "color": MUTED}, title_font={"size": 12, "color": MUTED}, title_standoff=10)
    return fig


def risk_distribution_chart(plan: pd.DataFrame) -> go.Figure:
    """Histogram of scores, coloured by action band, with the band thresholds marked."""
    frame = pd.DataFrame(
        {
            "score": pd.to_numeric(plan["predicted_risk"], errors="coerce"),
            "length": pd.to_numeric(plan["length_m"], errors="coerce").fillna(0),
        }
    ).dropna(subset=["score"])
    low = min(0.0, float(frame["score"].min())) if len(frame) else 0.0
    high = max(1.0, float(frame["score"].max())) if len(frame) else 1.0
    edges = np.linspace(low, high, int(round((high - low) / 0.05)) + 1)
    counts, _ = np.histogram(frame["score"], bins=edges)
    length_m, _ = np.histogram(frame["score"], bins=edges, weights=frame["length"])
    lengths = length_m / 1000
    centres = (edges[:-1] + edges[1:]) / 2

    def colour(value: float) -> str:
        if value >= RENEWAL_THRESHOLD:
            return RED
        if value >= INSPECT_THRESHOLD:
            return AMBER
        return GREEN

    fig = go.Figure(
        go.Bar(
            x=centres,
            y=counts,
            width=0.045,
            marker_color=[colour(value) for value in centres],
            customdata=np.column_stack([edges[:-1], edges[1:], lengths]),
            hovertemplate="Score %{customdata[0]:.2f} to %{customdata[1]:.2f}<br>%{y} segments<br>%{customdata[2]:.2f} km<extra></extra>",
        )
    )
    for threshold, label in ((INSPECT_THRESHOLD, "Inspect"), (RENEWAL_THRESHOLD, "Renewal Review")):
        fig.add_vline(x=threshold, line_dash="dot", line_color="#94A3B8", line_width=1)
        fig.add_annotation(
            x=threshold, y=1, yref="paper", text=f"{label} {threshold:.2f}", showarrow=False,
            xanchor="left", yanchor="top", xshift=4, font={"size": 11, "color": MUTED},
        )
    fig.update_layout(xaxis_title="Risk score", yaxis_title="Pipe segments", bargap=0.05)
    fig.update_xaxes(range=[low, high], dtick=0.1)
    return _layout(fig, 300)


def band_chart(plan: pd.DataFrame) -> go.Figure:
    order = [BAND_HIGH, BAND_MODERATE, BAND_LOW]
    counts = plan["risk_band"].value_counts().reindex(order).fillna(0).astype(int)
    fig = go.Figure(
        go.Bar(
            x=list(counts.index),
            y=counts.to_list(),
            marker_color=[BAND_COLORS[band] for band in counts.index],
            text=counts.to_list(),
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}<br>%{y} segments<extra></extra>",
        )
    )
    fig.update_layout(yaxis_title="Segments")
    return _layout(fig, 300)


def action_chart(plan: pd.DataFrame) -> go.Figure:
    order = [ACTION_RENEWAL, ACTION_INSPECT, ACTION_MONITOR]
    selected = plan.loc[plan["selected"]]
    counts = selected["recommended_action"].value_counts().reindex(order).fillna(0).astype(int)
    fig = go.Figure(
        go.Bar(
            x=list(counts.index),
            y=counts.to_list(),
            marker_color=[ACTION_COLORS[action] for action in counts.index],
            text=counts.to_list(),
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}<br>%{y} funded segments<extra></extra>",
        )
    )
    fig.update_layout(yaxis_title="Funded segments")
    return _layout(fig, 300)


def budget_walk_chart(plan: pd.DataFrame, budget_m: float) -> go.Figure:
    ordered = plan.sort_values("rank")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=ordered["rank"],
            y=ordered["cumulative_selected_m"] / 1000,
            mode="lines",
            line={"color": TEAL_DEEP, "width": 2.4, "shape": "hv"},
            fill="tozeroy",
            fillcolor="rgba(20, 184, 166, 0.10)",
            customdata=ordered["pipe_id"],
            hovertemplate="Rank %{x} (%{customdata})<br>%{y:.2f} km funded so far<extra></extra>",
        )
    )
    fig.add_hline(
        y=budget_m / 1000,
        line_dash="dot",
        line_color=NAVY,
        line_width=1.2,
        annotation_text=f"Budget {budget_m / 1000:.2f} km",
        annotation_position="top left",
        annotation_font={"size": 11, "color": MUTED},
    )
    fig.update_layout(xaxis_title="Rank", yaxis_title="Kilometres funded")
    return _layout(fig, 240)


def component_chart(row: pd.Series) -> go.Figure | None:
    if row.get("score_source") != "screening_heuristic":
        return None
    labels = ["Installation age", "Material", "Recorded breaks"]
    values = [row["age_component"], row["material_component"], row["break_component"]]
    fig = go.Figure(
        go.Bar(
            y=labels[::-1],
            x=values[::-1],
            orientation="h",
            marker_color=[TEAL_DEEP, NAVY, AMBER][::-1],
            text=[f"{value:.2f}" for value in values][::-1],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>%{x:.2f} points<extra></extra>",
        )
    )
    fig.update_layout(xaxis_title="Points (total capped at 1.00)", xaxis_range=[0, 0.6], bargap=0.45)
    _layout(fig, 230)
    fig.update_layout(margin={"l": 128, "r": 24, "t": 12, "b": 52})
    return fig


def break_history_chart(history: pd.DataFrame) -> go.Figure:
    counts = history.groupby("break_year")["break_count"].sum().reset_index()
    fig = go.Figure(
        go.Bar(
            x=counts["break_year"],
            y=counts["break_count"],
            marker_color=NAVY,
            hovertemplate="Year %{x}<br>%{y} recorded breaks<extra></extra>",
        )
    )
    fig.update_layout(xaxis_title="Year", yaxis_title="Recorded breaks")
    fig.update_yaxes(dtick=1)
    return _layout(fig, 230)


def capture_rate_chart(result: dict) -> go.Figure:
    """Capture rate for both plans at the user's budget and at the fixed fraction."""
    fraction = f"{result['capture_fraction']:.0%} of network"
    groups = ["Your budget", fraction]
    fig = go.Figure()
    for strategy, name, colour in (("jagapaip", "JagaPaip", TEAL_DEEP), ("oldest_first", "Oldest-first", NAVY)):
        values = [result["at_budget"][strategy]["capture_rate"], result["at_capture"][strategy]["capture_rate"]]
        shown = [None if value is None else 100 * value for value in values]
        fig.add_trace(
            go.Bar(
                name=name,
                x=groups,
                y=shown,
                marker_color=colour,
                text=["n/a" if value is None else f"{value:.1f}%" for value in shown],
                textposition="outside",
                cliponaxis=False,
                hovertemplate=f"{name}<br>%{{x}}<br>%{{y:.1f}}% of window breaks<extra></extra>",
            )
        )
    fig.update_layout(barmode="group", yaxis_title="Capture rate (%)", showlegend=True)
    _layout(fig, 280)
    fig.update_layout(showlegend=True, legend={"orientation": "h", "y": 1.12, "x": 0}, margin={"l": 64, "r": 16, "t": 36, "b": 40})
    return fig


def plan_compare_chart(comparison: dict) -> go.Figure:
    """Side-by-side plan composition. Not an outcome or savings chart."""
    ours = comparison["jagapaip"]
    base = comparison["oldest_first"]
    network_m = comparison.get("network_m") or 0.0
    budget_m = comparison.get("budget_m") or 0.0
    groups = [
        "Length used (km)",
        "High-risk segments covered",
        "Score mass in plan",
    ]
    fig = go.Figure()
    for name, colour, values in (
        (
            "JagaPaip",
            TEAL_DEEP,
            [
                ours["length_m"] / 1000,
                ours["high_risk_selected"],
                ours["score_sum"],
            ],
        ),
        (
            "Oldest-first",
            NAVY,
            [
                base["length_m"] / 1000,
                base["high_risk_selected"],
                base["score_sum"],
            ],
        ),
    ):
        fig.add_trace(
            go.Bar(
                name=name,
                x=groups,
                y=values,
                marker_color=colour,
                text=[f"{value:.2f}" if isinstance(value, float) else f"{value}" for value in values],
                textposition="outside",
                cliponaxis=False,
                hovertemplate=f"{name}<br>%{{x}}<br>%{{y:.2f}}<extra></extra>",
            )
        )
    fig.update_layout(barmode="group", yaxis_title="Plan composition (mixed units)", showlegend=True)
    _layout(fig, 280)
    fig.update_layout(
        showlegend=True,
        legend={"orientation": "h", "y": 1.12, "x": 0},
        margin={"l": 64, "r": 16, "t": 36, "b": 40},
    )
    if budget_m > 0:
        fig.add_annotation(
            text=f"Same length budget: {budget_m / 1000:.2f} km of {network_m / 1000:.2f} km eligible",
            xref="paper",
            yref="paper",
            x=0,
            y=-0.22,
            showarrow=False,
            font={"size": 11, "color": MUTED},
        )
    return fig


def selection_overlap_chart(comparison: dict) -> go.Figure:
    counts = [
        len(comparison["only_jagapaip"]),
        len(comparison["overlap_ids"]),
        len(comparison["only_oldest"]),
    ]
    fig = go.Figure(
        go.Bar(
            x=["JagaPaip only", "Both plans", "Oldest-first only"],
            y=counts,
            marker_color=[TEAL_DEEP, AMBER, NAVY],
            text=counts,
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}<br>%{y} segments<extra></extra>",
        )
    )
    fig.update_layout(yaxis_title="Selected segments", bargap=0.45)
    return _layout(fig, 260)


def capture_chart(jagapaip_breaks: int, baseline_breaks: int) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=["JagaPaip plan", "Oldest-first baseline"],
            y=[jagapaip_breaks, baseline_breaks],
            marker_color=[TEAL_DEEP, NAVY],
            text=[jagapaip_breaks, baseline_breaks],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}<br>%{y} recorded breaks in the outcome window<extra></extra>",
        )
    )
    fig.update_layout(yaxis_title="Recorded breaks", bargap=0.55)
    return _layout(fig, 280)
