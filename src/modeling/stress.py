"""Robustness stress tests: does the ranking survive missing or noisy inputs?

Each method is fitted once per fold on clean training years, then scores the
test year clean and under each corruption scenario. Evaluation always uses
the true lengths and outcomes, so only the model's inputs are disturbed.
Confidence is recomputed on the corrupted rows to check that damaged
records are downgraded rather than trusted.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .budget import evaluate_budget, selected_segments
from .confidence import assess_confidence
from .config import CANDIDATE_METHODS, MIN_TRAIN_YEARS, PRIMARY_BUDGET, SEED, TARGET, budget_key
from .features import numeric
from .methods import RANKERS
from .splits import split_frame, walk_forward_folds
from .summaries import mean_or_none, round_or_none

MASKABLE_COLUMNS = ("material", "diameter_mm", "install_year", "nearby_prior_breaks")


def _mask(test: pd.DataFrame, rate: float, rng) -> tuple[pd.DataFrame, np.ndarray]:
    """Hide each maskable value independently with probability ``rate``."""
    out = test.copy()
    affected = np.zeros(len(out), dtype=bool)
    for col in MASKABLE_COLUMNS:
        if col not in out:
            continue
        hit = rng.random(len(out)) < rate
        affected |= hit
        if col == "material":
            out[col] = out[col].where(~hit, "UNKNOWN")
        elif col == "install_year":
            out["install_year"] = numeric(out["install_year"]).where(~hit)
            out["age_years"] = numeric(out["age_years"]).where(~hit)
        else:
            out[col] = numeric(out[col]).where(~hit)
    return out, affected


def _novel_material(test: pd.DataFrame, rate: float, rng) -> tuple[pd.DataFrame, np.ndarray]:
    out = test.copy()
    hit = rng.random(len(out)) < rate
    out["material"] = out["material"].where(~hit, "NOVEL_MATERIAL")
    return out, hit


def _perturb_numeric(test: pd.DataFrame, rng) -> tuple[pd.DataFrame, np.ndarray]:
    """Install year off by up to +/-2 years (never after the score year); length off by up to +/-5%."""
    out = test.copy()
    score_year = numeric(out["score_year"])
    install = np.minimum(numeric(out["install_year"]) + rng.integers(-2, 3, size=len(out)), score_year)
    out["install_year"] = install
    out["age_years"] = score_year - install
    out["length_m"] = numeric(out["length_m"]) * rng.uniform(0.95, 1.05, size=len(out))
    return out, np.ones(len(out), dtype=bool)


SCENARIOS = {
    "mask_05": (
        "Hide 5% of material, diameter, install-year and nearby-break values",
        lambda test, rng: _mask(test, 0.05, rng),
    ),
    "mask_10": (
        "Hide 10% of material, diameter, install-year and nearby-break values",
        lambda test, rng: _mask(test, 0.10, rng),
    ),
    "unseen_material_05": (
        "Replace 5% of materials with a value never seen in training",
        lambda test, rng: _novel_material(test, 0.05, rng),
    ),
    "perturb_numeric": (
        "Shift install years by up to 2 years and lengths by up to 5%",
        _perturb_numeric,
    ),
}


def _ranked(truth: pd.DataFrame, scores) -> pd.DataFrame:
    scores = np.asarray(scores, dtype=float)
    return truth.assign(
        model_score=scores,
        risk_percentile=pd.Series(scores).rank(method="average", pct=True).to_numpy(),
    )


def _spearman(a: pd.Series, b: pd.Series) -> float | None:
    a, b = pd.Series(np.asarray(a)), pd.Series(np.asarray(b))
    if a.nunique() < 2 or b.nunique() < 2:
        return None
    return float(a.corr(b, method="spearman"))


def _jaccard(a: pd.Series, b: pd.Series) -> float | None:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else None


def run_stress_tests(
    panel: pd.DataFrame,
    test_years,
    *,
    seed: int = SEED,
    methods=CANDIDATE_METHODS,
    budget: float = PRIMARY_BUDGET,
    min_train_years: int = MIN_TRAIN_YEARS,
    rankers=None,
) -> dict:
    rankers = RANKERS if rankers is None else rankers
    records = []
    affected_labels: dict[str, list[np.ndarray]] = {name: [] for name in SCENARIOS}
    for fold in walk_forward_folds(panel["score_year"].unique(), test_years, min_train_years):
        train, test = split_frame(panel, fold)
        features = test.drop(columns=[TARGET])
        truth = pd.DataFrame(
            {
                "segment_id": test["segment_id"].astype(str).to_numpy(),
                "length_m": numeric(test["length_m"]).to_numpy(),
                "actual_break": test[TARGET].astype("int64").to_numpy(),
            }
        )
        fitted = {method: rankers[method](seed=seed).fit(train) for method in methods}
        clean = {method: _ranked(truth, fitted[method].score(features)) for method in methods}
        for index, (name, (_, corrupt)) in enumerate(SCENARIOS.items()):
            corrupted, affected = corrupt(features, np.random.default_rng([seed, fold.test_year, index]))
            labels = assess_confidence(train, corrupted)["confidence_label"].to_numpy()
            affected_labels[name].append(labels[affected])
            for method in methods:
                stressed = _ranked(truth, fitted[method].score(corrupted))
                records.append(
                    {
                        "scenario": name,
                        "method": method,
                        "capture": evaluate_budget(stressed, budget).capture,
                        "clean_capture": evaluate_budget(clean[method], budget).capture,
                        "spearman": _spearman(clean[method]["model_score"], stressed["model_score"]),
                        "overlap": _jaccard(
                            selected_segments(clean[method], budget), selected_segments(stressed, budget)
                        ),
                    }
                )

    table = pd.DataFrame(records)
    key = budget_key(budget)
    scenarios = {}
    for name, (description, _) in SCENARIOS.items():
        labels = np.concatenate(affected_labels[name])
        per_method = {}
        for method, rows in table[table["scenario"] == name].groupby("method", sort=True):
            capture, clean_capture = mean_or_none(rows["capture"]), mean_or_none(rows["clean_capture"])
            per_method[method] = {
                f"capture_at_{key}": round_or_none(capture),
                f"capture_at_{key}_change": (
                    round_or_none(capture - clean_capture)
                    if capture is not None and clean_capture is not None
                    else None
                ),
                "spearman_rank_corr": round_or_none(mean_or_none(rows["spearman"])),
                f"selection_overlap_at_{key}": round_or_none(mean_or_none(rows["overlap"])),
            }
        scenarios[name] = {
            "description": description,
            "affected_rows": int(len(labels)),
            "affected_rows_confidence": (
                {label: round_or_none((labels == label).mean(), 4) for label in ("HIGH", "MEDIUM", "LOW")}
                if len(labels)
                else {}
            ),
            "methods": per_method,
        }
    return {
        "budget": budget,
        "note": "models are fitted on clean training years; only test-year inputs are corrupted; "
        "evaluation uses true lengths and outcomes",
        "scenarios": scenarios,
    }
