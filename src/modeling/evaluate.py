"""Walk-forward evaluation: Contract A in, Contract B and metrics.json out.

For each test year Y, every method is trained on score years < Y, scores the
eligible segments of year Y, and is judged against the same network-length
budgets. metrics.json is computed from exactly the predictions written to
Contract B, so Proof Mode counters always reconcile with it.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from .budget import evaluate_budget
from .confidence import assess_confidence
from .config import (
    BASELINE_METHODS,
    BUDGETS,
    CANDIDATE_METHODS,
    CHAMPION_SELECTION_RULE,
    CONTRACT_METHODS,
    MIN_TRAIN_YEARS,
    PRIMARY_BUDGET,
    SCHEMA_VERSION,
    SEED,
    SELECTION_RULE,
    SELECTION_UNIT,
    TARGET,
    budget_key,
    budget_label,
)
from .features import numeric
from .methods import RANKERS, Ranker
from .splits import default_test_years, last_complete_year, split_frame, walk_forward_folds

CONTRACT_B_COLUMNS = [
    "segment_id",
    "test_year",
    "method",
    "model_score",
    "risk_percentile",
    "confidence_label",
    "is_ood",
    "actual_break",
    "length_m",
]

SYNTHETIC_WARNING = (
    "SYNTHETIC FIXTURE DATA: these numbers are schema examples, not results. "
    "Never show them on slides or in Proof Mode."
)
LIMITATIONS = [
    "Capture counts segments with at least one recorded break in the test year, not individual break events.",
    "A selected segment without a recorded break is an observed non-event, not proof that acting on it was unnecessary.",
    "Results measure targeting quality at a fixed network-length budget, not breaks prevented or money saved.",
    "risk_percentile is a within-year ranking, not a calibrated probability.",
    "The random baseline is a single seeded draw per test year.",
    "Features come from a current-inventory snapshot; pipes replaced before the snapshot are absent (survivorship). See docs/data-card.md.",
    "Validated on City of Kitchener open data only; performance in Malaysia is untested.",
]


@dataclass
class EvaluationResult:
    contract_b: pd.DataFrame
    metrics: dict
    predictions: pd.DataFrame  # every evaluated method, long format
    year_table: pd.DataFrame  # one row per test_year x method x budget


def prepare_panel(
    pipe_year: pd.DataFrame, exclude_ambiguous: bool = True, complete_through: int | None = None
) -> pd.DataFrame:
    """Rows for score years after ``complete_through`` are dropped because their
    outcomes are not fully observed yet. The primary panel also drops ambiguous
    histories; the sensitivity panel keeps them but blanks negative ages,
    which cannot be valid features."""
    if complete_through is not None:
        pipe_year = pipe_year[pipe_year["score_year"] <= complete_through]
    if exclude_ambiguous:
        return pipe_year[~pipe_year["is_ambiguous_history"].astype(bool)].copy()
    panel = pipe_year.copy()
    age = numeric(panel["age_years"])
    panel["age_years"] = age.where(~(age < 0))
    return panel


def predict_walk_forward(
    panel: pd.DataFrame,
    test_years,
    *,
    seed: int = SEED,
    rankers: dict[str, type[Ranker]] | None = None,
    min_train_years: int = MIN_TRAIN_YEARS,
) -> pd.DataFrame:
    """Long-format predictions for every ranker and test year (Contract B columns)."""
    rankers = RANKERS if rankers is None else rankers
    frames = []
    for fold in walk_forward_folds(panel["score_year"].unique(), test_years, min_train_years):
        train, test = split_frame(panel, fold)
        features = test.drop(columns=[TARGET])
        confidence = assess_confidence(train, features)
        for name, ranker_cls in rankers.items():
            scores = np.asarray(ranker_cls(seed=seed).fit(train).score(features), dtype=float)
            if scores.shape != (len(test),) or not np.isfinite(scores).all():
                raise ValueError(f"{name} returned invalid scores for {fold.test_year}")
            frames.append(
                pd.DataFrame(
                    {
                        "segment_id": test["segment_id"].astype(str).to_numpy(),
                        "test_year": np.full(len(test), fold.test_year, dtype="int64"),
                        "method": name,
                        "model_score": scores,
                        "risk_percentile": pd.Series(scores).rank(method="average", pct=True).to_numpy(),
                        "confidence_label": confidence["confidence_label"].to_numpy(),
                        "is_ood": confidence["is_ood"].to_numpy(dtype=bool),
                        "actual_break": test[TARGET].astype("int64").to_numpy(),
                        "length_m": numeric(test["length_m"]).to_numpy(),
                    }
                )
            )
    return pd.concat(frames, ignore_index=True)


def score_years(predictions: pd.DataFrame, budgets=BUDGETS) -> pd.DataFrame:
    """One row per test_year x method x budget, plus PR-AUC as a diagnostic."""
    records = []
    for (year, method), group in predictions.groupby(["test_year", "method"], sort=True):
        actual = group["actual_break"].to_numpy(dtype=int)
        has_both_classes = 0 < actual.sum() < len(actual)
        pr_auc = float(average_precision_score(actual, group["model_score"])) if has_both_classes else None
        for budget in budgets:
            records.append(
                {
                    "test_year": int(year),
                    "method": method,
                    "eligible_segments": len(group),
                    "pr_auc": pr_auc,
                    **asdict(evaluate_budget(group, budget)),
                }
            )
    table = pd.DataFrame(records)
    _assert_equal_budgets(table)
    return table


def _assert_equal_budgets(table: pd.DataFrame) -> None:
    """Every method in a year must be judged against the same network length."""
    distinct = table.groupby(["test_year", "budget"])["budget_length_m"].nunique()
    if (distinct > 1).any():
        raise AssertionError(f"unequal length budgets across methods:\n{distinct[distinct > 1]}")


def _r(value, digits: int = 6):
    if value is None:
        return None
    value = float(value)
    return None if math.isnan(value) else round(value, digits)


def _mean(values) -> float | None:
    s = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    return float(s.mean()) if len(s) else None


def summarize_methods(table: pd.DataFrame, budgets=BUDGETS) -> dict:
    primary = budget_key(PRIMARY_BUDGET)
    capture_key = f"capture_at_{primary}"
    summary = {}
    for method, group in table.groupby("method", sort=True):
        entry = {}
        for budget in budgets:
            at = group[group["budget"] == budget]
            key = budget_key(budget)
            entry[f"capture_at_{key}"] = _mean(at["capture"])
            entry[f"precision_at_{key}"] = _mean(at["precision"])
            entry[f"observed_non_events_at_{key}"] = int(at["observed_non_events"].sum())
        yearly = pd.to_numeric(group.loc[group["budget"] == PRIMARY_BUDGET, "capture"], errors="coerce").dropna()
        entry[f"{capture_key}_std"] = float(yearly.std(ddof=1)) if len(yearly) > 1 else None
        entry[f"{capture_key}_min"] = float(yearly.min()) if len(yearly) else None
        entry[f"{capture_key}_max"] = float(yearly.max()) if len(yearly) else None
        entry["pr_auc_mean"] = _mean(group.drop_duplicates("test_year")["pr_auc"])
        summary[method] = entry

    yearly_capture = table[table["budget"] == PRIMARY_BUDGET].pivot(
        index="test_year", columns="method", values="capture"
    ).apply(pd.to_numeric, errors="coerce")
    for method, entry in summary.items():
        for reference in ("oldest", "random"):
            base = summary.get(reference, {}).get(capture_key)
            value = entry[capture_key]
            entry[f"lift_vs_{reference}_at_{primary}"] = value / base if value is not None and base else None
        if "oldest" in yearly_capture:
            beats = yearly_capture[method] > yearly_capture["oldest"]
            entry[f"years_beating_oldest_at_{primary}"] = int(beats.sum())
    return {m: {k: _r(v) if isinstance(v, float) else v for k, v in e.items()} for m, e in summary.items()}


def select_champion(summary: dict) -> str:
    key = f"capture_at_{budget_key(PRIMARY_BUDGET)}"
    champion, best = None, -math.inf
    for method in CANDIDATE_METHODS:  # simplest first, so a tie keeps the simpler method
        value = summary.get(method, {}).get(key)
        if value is not None and round(value, 4) > best:
            champion, best = method, round(value, 4)
    if champion is None:
        raise ValueError("no candidate method produced a primary-budget capture")
    return champion


def build_contract_b(predictions: pd.DataFrame, champion: str) -> pd.DataFrame:
    baselines = predictions[predictions["method"].isin(BASELINE_METHODS)]
    champion_rows = predictions[predictions["method"] == champion].assign(method="champion")
    out = pd.concat([baselines, champion_rows], ignore_index=True)
    method_rank = out["method"].map({m: i for i, m in enumerate(CONTRACT_METHODS)})
    out = (
        out.assign(_method_rank=method_rank)
        .sort_values(
            ["test_year", "_method_rank", "risk_percentile", "segment_id"],
            ascending=[True, True, False, True],
        )
        .drop(columns="_method_rank")
    )
    return out[CONTRACT_B_COLUMNS].reset_index(drop=True)


def _year_cell(row) -> dict:
    return {
        "budget_length_m": _r(row.budget_length_m, 3),
        "selected_segments": int(row.selected_segments),
        "selected_length_m": _r(row.selected_length_m, 3),
        "breaks_captured": int(row.breaks_captured),
        "total_breaks": int(row.total_breaks),
        "capture": _r(row.capture),
        "precision": _r(row.precision),
        "observed_non_events": int(row.observed_non_events),
    }


def build_by_year(table: pd.DataFrame, champion: str, budgets=BUDGETS) -> dict:
    by_year = {}
    for year, rows in table.groupby("test_year", sort=True):
        first = rows.iloc[0]
        entry = {
            "summary": {
                "eligible_segments": int(first["eligible_segments"]),
                "network_length_m": _r(first["network_length_m"], 3),
                "total_breaks": int(first["total_breaks"]),
            }
        }
        for budget in budgets:
            cells = {row.method: _year_cell(row) for row in rows[rows["budget"] == budget].itertuples(index=False)}
            cells["champion"] = cells[champion]
            entry[budget_label(budget)] = cells
        pr_auc = {m: _r(v) for m, v in rows.drop_duplicates("method").set_index("method")["pr_auc"].items()}
        pr_auc["champion"] = pr_auc[champion]
        entry["pr_auc"] = pr_auc
        by_year[str(int(year))] = entry
    return by_year


def _outcomes_complete_through(pipe_year: pd.DataFrame, is_synthetic: bool) -> int:
    complete_through = last_complete_year(pipe_year["source_snapshot_date"])
    if complete_through is not None:
        return complete_through
    if is_synthetic:
        return int(pipe_year["score_year"].max())  # the generator simulates whole years
    raise ValueError(
        "source_snapshot_date must be a date so that incomplete outcome years can be excluded"
    )


def _ambiguity_sensitivity(
    pipe_year, exclude_ambiguous, complete_through, test_years, seed, budgets, min_train_years, rankers
):
    in_window = pipe_year["score_year"] <= complete_through
    n_ambiguous = int(pipe_year.loc[in_window, "is_ambiguous_history"].astype(bool).sum())
    if n_ambiguous == 0:
        return {"ambiguous_rows": 0, "note": "no ambiguous histories in the input"}
    alternative = prepare_panel(pipe_year, not exclude_ambiguous, complete_through)
    predictions = predict_walk_forward(
        alternative, test_years, seed=seed, rankers=rankers, min_train_years=min_train_years
    )
    summary = summarize_methods(score_years(predictions, budgets), budgets)
    key = f"capture_at_{budget_key(PRIMARY_BUDGET)}"
    return {
        "ambiguous_rows": n_ambiguous,
        "variant": "ambiguous histories included" if exclude_ambiguous else "ambiguous histories excluded",
        key: {method: entry[key] for method, entry in summary.items()},
    }


def run_evaluation(
    pipe_year: pd.DataFrame,
    *,
    test_years=None,
    seed: int = SEED,
    budgets=BUDGETS,
    exclude_ambiguous: bool = True,
    run_sensitivity: bool = True,
    is_synthetic: bool | None = None,
    min_train_years: int = MIN_TRAIN_YEARS,
    rankers: dict[str, type[Ranker]] | None = None,
) -> EvaluationResult:
    snapshots = sorted(pipe_year["source_snapshot_date"].astype(str).unique())
    if is_synthetic is None:
        is_synthetic = any("SYNTHETIC" in s.upper() for s in snapshots)
    complete_through = _outcomes_complete_through(pipe_year, is_synthetic)
    if test_years and (too_recent := sorted(int(y) for y in test_years if int(y) > complete_through)):
        raise ValueError(
            f"test years {too_recent} are incomplete: the data snapshot ({', '.join(snapshots)}) "
            f"only covers outcomes through {complete_through}"
        )
    incomplete_years = sorted(int(y) for y in pipe_year["score_year"].unique() if y > complete_through)

    panel = prepare_panel(pipe_year, exclude_ambiguous, complete_through)
    years = sorted(int(y) for y in panel["score_year"].unique())
    test_years = sorted(int(y) for y in (test_years or default_test_years(years, min_train_years=min_train_years)))

    predictions = predict_walk_forward(
        panel, test_years, seed=seed, rankers=rankers, min_train_years=min_train_years
    )
    table = score_years(predictions, budgets)
    methods = summarize_methods(table, budgets)
    champion = select_champion(methods)
    methods["champion"] = dict(methods[champion])

    metrics = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_snapshot": ", ".join(snapshots),
        "is_synthetic": bool(is_synthetic),
        "selection_unit": SELECTION_UNIT,
        "selection_rule": SELECTION_RULE,
        "champion_method": champion,
        "champion_selection_rule": CHAMPION_SELECTION_RULE,
        "candidate_methods": [m for m in CANDIDATE_METHODS if m in methods],
        "test_years": test_years,
        "budgets": list(budgets),
        "primary_budget": PRIMARY_BUDGET,
        "aggregation": {
            "capture_at_XX": "mean across test years (years without recorded breaks are skipped)",
            "precision_at_XX": "mean across test years",
            "observed_non_events_at_XX": "sum across test years",
        },
        "methods": methods,
        "by_year": build_by_year(table, champion, budgets),
        "sensitivity": (
            _ambiguity_sensitivity(
                pipe_year, exclude_ambiguous, complete_through, test_years, seed, budgets, min_train_years, rankers
            )
            if run_sensitivity
            else {"note": "not run"}
        ),
        "inputs": {
            "contract_a_rows": int(len(pipe_year)),
            "panel_rows": int(len(panel)),
            "ambiguous_histories": "excluded" if exclude_ambiguous else "included",
            "score_years": [years[0], years[-1]],
            "outcomes_complete_through": complete_through,
            "incomplete_score_years_excluded": incomplete_years,
            "seed": seed,
        },
        "limitations": ([SYNTHETIC_WARNING] if is_synthetic else []) + LIMITATIONS,
    }
    return EvaluationResult(
        contract_b=build_contract_b(predictions, champion),
        metrics=metrics,
        predictions=predictions,
        year_table=table,
    )
