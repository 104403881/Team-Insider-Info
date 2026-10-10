"""Proof Mode on the team's contracts: Contract B rankings, metrics.json numbers.

When fold_predictions (Contract B) and metrics.json are loaded, Proof Mode
shows Member 2's measured walk-forward result instead of an app-side
backtest. Plans come straight from Contract B with the frozen selection
rule, and every displayed count or rate is read from metrics.json. The app
rebuilds the plans only to list the selected pipes and to check that they
reproduce metrics.json; a mismatch is reported, never silently shown.
"""

from __future__ import annotations

import math

import pandas as pd

from jagapaip.schema import CONTRACT_CHAMPION, CONTRACT_OLDEST

PROOF_METHODS = (CONTRACT_CHAMPION, CONTRACT_OLDEST)


def budget_label(budget: float) -> str:
    """0.05 -> 'budget_0.05', the by_year key used in metrics.json."""
    return f"budget_{budget:.2f}"


def budget_key(budget: float) -> str:
    """0.05 -> '05', as in capture_at_05."""
    return f"{round(budget * 100):02d}"


def contract_years(metrics: dict) -> list[int]:
    return [int(year) for year in metrics.get("test_years", [])]


def contract_budgets(metrics: dict) -> list[float]:
    return [float(budget) for budget in metrics.get("budgets", [])]


def contract_plan(contract_b: pd.DataFrame, year: int, method: str, budget: float) -> pd.DataFrame:
    """One method's ranked list for one test year, with the frozen budget rule.

    Order: risk_percentile descending, then segment_id ascending. Selected:
    the longest prefix whose cumulative length_m does not exceed
    budget x total length_m of that year's rows. Stops at the first overflow.
    """
    rows = contract_b.loc[(contract_b["test_year"] == year) & (contract_b["method"] == method)].copy()
    rows["segment_id"] = rows["segment_id"].astype(str)
    rows = rows.sort_values(["risk_percentile", "segment_id"], ascending=[False, True]).reset_index(drop=True)
    lengths = pd.to_numeric(rows["length_m"], errors="coerce").astype(float)
    budget_length = budget * math.fsum(lengths)
    rows["rank"] = range(1, len(rows) + 1)
    rows["cumulative_length_m"] = lengths.cumsum()
    rows["selected"] = rows["cumulative_length_m"] <= budget_length
    rows["budget_length_m"] = budget_length
    return rows


def contract_plans(contract_b: pd.DataFrame, year: int, budget: float) -> dict[str, pd.DataFrame]:
    return {method: contract_plan(contract_b, year, method, budget) for method in PROOF_METHODS}


def metrics_cell(metrics: dict, year: int, budget: float, method: str) -> dict | None:
    """metrics.json -> by_year[year][budget][method], or None if absent."""
    return metrics.get("by_year", {}).get(str(year), {}).get(budget_label(budget), {}).get(method)


def plan_mismatches(plans: dict[str, pd.DataFrame], metrics: dict, year: int, budget: float, revealed: bool) -> list[str]:
    """Differences between the app's rebuilt plans and metrics.json.

    Before the reveal only the selection itself is compared; after it, the
    captured breaks are compared too.
    """
    problems = []
    for method, plan in plans.items():
        cell = metrics_cell(metrics, year, budget, method)
        if cell is None:
            problems.append(f"metrics.json has no {year} {budget_label(budget)} entry for {method}.")
            continue
        chosen = plan.loc[plan["selected"]]
        if len(chosen) != cell.get("selected_segments"):
            problems.append(f"{method}: {len(chosen)} segments selected, metrics.json says {cell.get('selected_segments')}.")
        if not math.isclose(float(chosen["length_m"].sum()), float(cell.get("selected_length_m", -1)), abs_tol=0.5):
            problems.append(f"{method}: selected length differs from metrics.json.")
        if revealed and "actual_break" in chosen.columns:
            captured = int(pd.to_numeric(chosen["actual_break"], errors="coerce").fillna(0).sum())
            if captured != cell.get("breaks_captured"):
                problems.append(f"{method}: {captured} breaks captured, metrics.json says {cell.get('breaks_captured')}.")
    return problems


def year_interval(metrics: dict, year: int, budget: float) -> list[float] | None:
    """Bootstrap interval for (champion - oldest) capture in one test year."""
    block = metrics.get("uncertainty", {}).get("difference_vs_oldest", {}).get(budget_label(budget), {})
    return (block.get(CONTRACT_CHAMPION) or {}).get("by_year", {}).get(str(year))


def across_years(metrics: dict, budget: float) -> pd.DataFrame:
    """Mean capture across test years with its bootstrap interval, per method."""
    key = f"capture_at_{budget_key(budget)}"
    capture_ci = metrics.get("uncertainty", {}).get("capture", {}).get(budget_label(budget), {})
    rows = []
    order = [CONTRACT_CHAMPION, CONTRACT_OLDEST, "prior_breaks", "random"]
    names = {CONTRACT_CHAMPION: f"JagaPaip champion ({metrics.get('champion_method', '?')})", CONTRACT_OLDEST: "Oldest-first"}
    for method in order:
        entry = metrics.get("methods", {}).get(method)
        if entry is None or (method == "prior_breaks" and metrics.get("champion_method") == "prior_breaks"):
            continue
        interval = (capture_ci.get(method) or {}).get("ci_mean")
        rows.append(
            {
                "Method": names.get(method, method.replace("_", " ").capitalize()),
                "Capture (mean of test years)": entry.get(key),
                "95% interval": None if not interval else f"{100 * interval[0]:.1f}% – {100 * interval[1]:.1f}%",
                "Years beating oldest-first": entry.get(f"years_beating_oldest_at_{budget_key(budget)}"),
            }
        )
    return pd.DataFrame(rows)
