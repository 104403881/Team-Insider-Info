"""Contract mode: Contract B drives the ranking and metrics.json drives Proof Mode."""

import json
from pathlib import Path

import pandas as pd
import pytest

from jagapaip.contract_proof import contract_budgets, contract_plan, contract_plans, contract_years, plan_mismatches
from jagapaip.loader import ROOT, load_dataset
from jagapaip.proof import features_for_year
from jagapaip.ranking import build_worklist
from jagapaip.schema import ACTION_INSPECT, ACTION_PENDING, STRATEGY_JAGAPAIP

REPO_ARTIFACTS = ROOT.parent / "artifacts"


def write_project(root: Path, worklist: pd.DataFrame | None = None, metrics: dict | None = None) -> None:
    """A tiny project: 4 pipes over 3 years; Contract B scores only P1-P3."""
    data = root / "data"
    data.mkdir()
    pipe_year = pd.DataFrame(
        [
            {"pipe_id": f"P{i}", "year": year, "install_year": 1950 + i, "length_m": 100.0,
             "material": "CI", "prior_break_count": i, "break_count": 0}  # P2 has more breaks than P1
            for i in range(1, 5)
            for year in (2023, 2024, 2025)
        ]
    )
    pipe_year.to_csv(data / "pipe_year.csv", index=False)
    scores = {  # risk_percentile per method; P1/P2 tie for the champion
        "champion": {"P1": 0.9, "P2": 0.9, "P3": 0.3},
        "oldest": {"P1": 1.0, "P2": 0.6, "P3": 0.3},
        "random": {"P1": 0.1, "P2": 0.5, "P3": 0.9},
        "prior_breaks": {"P1": 0.8, "P2": 0.5, "P3": 0.2},
    }
    rows = [
        {"segment_id": pid, "test_year": 2025, "method": method, "model_score": pct, "risk_percentile": pct,
         "confidence_label": "HIGH", "is_ood": False, "actual_break": int(pid == "P2"), "length_m": 100.0}
        for method, by_pipe in scores.items()
        for pid, pct in by_pipe.items()
    ]
    pd.DataFrame(rows).to_parquet(data / "fold_predictions.parquet", index=False)
    (data / "metrics.json").write_text(json.dumps(metrics or tiny_metrics()), encoding="utf-8")
    if worklist is not None:
        worklist.to_parquet(data / "ranked_worklists.parquet", index=False)


def tiny_metrics(champion_selected: int = 2) -> dict:
    cell = {"selected_segments": champion_selected, "selected_length_m": 100.0 * champion_selected,
            "breaks_captured": 1, "total_breaks": 1, "capture": 1.0}
    return {
        "schema_version": "1.0", "champion_method": "prior_breaks", "test_years": [2025], "budgets": [0.7],
        "by_year": {"2025": {"budget_0.70": {
            "champion": cell,
            "oldest": {"selected_segments": 2, "selected_length_m": 200.0, "breaks_captured": 1, "total_breaks": 1, "capture": 1.0},
        }}},
        "methods": {}, "limitations": [],
    }


def test_contract_b_champion_scores_are_used_and_methods_never_averaged(tmp_path):
    write_project(tmp_path)
    data = load_dataset(tmp_path)
    assert data["meta"]["contract_mode"] is True
    scores = data["predictions"].set_index("pipe_id")["predicted_risk"].to_dict()
    assert scores == {"P1": 0.9, "P2": 0.9, "P3": 0.3}


def test_worklist_follows_contract_order_and_skips_unscored_pipes(tmp_path):
    write_project(tmp_path)
    data = load_dataset(tmp_path)
    features = features_for_year(data, 2025)
    plan = build_worklist(features, budget_m=1_000, strategy=STRATEGY_JAGAPAIP)
    # Tie between P1 and P2 goes to pipe ID (contract), not to prior breaks; P4 has no score.
    assert plan["pipe_id"].tolist() == ["P1", "P2", "P3"]
    assert set(plan["score_source"]) == {"contract_champion"}


def test_actions_wait_for_contract_c(tmp_path):
    write_project(tmp_path)
    plan = build_worklist(features_for_year(load_dataset(tmp_path), 2025), budget_m=1_000)
    assert set(plan["recommended_action"]) == {ACTION_PENDING}


def test_actions_come_from_contract_c_when_published(tmp_path):
    worklist = pd.DataFrame(
        {"test_year": [2025] * 3, "method": ["champion"] * 3, "ranking_mode": ["VALIDATED_RISK"] * 3,
         "segment_id": ["P1", "P2", "P3"], "recommended_action": [ACTION_INSPECT, "Monitor", "Monitor"]}
    )
    write_project(tmp_path, worklist=worklist)
    plan = build_worklist(features_for_year(load_dataset(tmp_path), 2025), budget_m=1_000)
    assert plan.set_index("pipe_id")["recommended_action"].to_dict() == {"P1": ACTION_INSPECT, "P2": "Monitor", "P3": "Monitor"}


def test_contract_plan_stops_at_first_overflow(tmp_path):
    write_project(tmp_path)
    contract_b = load_dataset(tmp_path)["contract_b"]
    # 70% of 300 m = 210 m: P1 + P2 = 200 m fit, P3 would overflow.
    plan = contract_plan(contract_b, 2025, "champion", 0.7)
    assert plan.loc[plan["selected"], "segment_id"].tolist() == ["P1", "P2"]


def test_plan_check_passes_on_matching_metrics_and_flags_a_mismatch(tmp_path):
    write_project(tmp_path)
    data = load_dataset(tmp_path)
    plans = contract_plans(data["contract_b"], 2025, 0.7)
    assert plan_mismatches(plans, data["metrics"], 2025, 0.7, revealed=True) == []
    wrong = tiny_metrics(champion_selected=3)
    assert plan_mismatches(plans, wrong, 2025, 0.7, revealed=True)


@pytest.mark.skipif(not (REPO_ARTIFACTS / "metrics.json").exists(), reason="team artifacts not present")
def test_real_artifacts_reproduce_metrics_json_for_every_year_and_budget():
    data = load_dataset(ROOT)
    assert data["meta"]["contract_mode"] is True
    metrics, contract_b = data["metrics"], data["contract_b"]
    for year in contract_years(metrics):
        for budget in contract_budgets(metrics):
            plans = contract_plans(contract_b, year, budget)
            assert plan_mismatches(plans, metrics, year, budget, revealed=True) == [], (year, budget)
