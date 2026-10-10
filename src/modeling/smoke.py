"""End-to-end smoke test for the integration gates (Member 2 is deputy integrator).

Run from the repo root:
    python -m src.modeling.smoke               # contract + app checks on artifacts/
    python -m src.modeling.smoke --reproduce   # also rebuild B + metrics.json from data/ and compare
    python -m src.modeling.smoke --run-tests   # also run every lane's pytest suite

Each check prints PASS, WARN, FAIL or SKIP. The exit code is 1 if anything
fails, so the command can gate a merge or a freeze.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .config import TARGET, budget_label
from .contracts import (
    metrics_consistency_errors,
    validate_fold_predictions,
    validate_metrics,
    validate_pipe_year,
)
from .evaluate import select_champion

REPO = Path(__file__).resolve().parents[2]
AGREED_TEST_YEARS = [2023, 2024, 2025]  # kickoff decision: 2025 demo year, 2024/2023 backups

# Contract C (TEAM_EXECUTION_PLAN.md section 4), owned by Member 3.
CONTRACT_C_COLUMNS = {
    "test_year": "integer", "method": "string", "ranking_mode": "string", "segment_id": "string",
    "priority_rank": "integer", "cumulative_length_m": "float", "risk_percentile": "float",
    "risk_pattern": "string", "confidence_label": "string", "consequence_index": "float",
    "recommended_action": "string", "reason_short": "string", "actual_break": "integer",
}
RANKING_MODES = {"VALIDATED_RISK", "SCENARIO_CONSEQUENCE"}
ACTIONS = {"MONITOR", "INSPECT", "RENEWAL_REVIEW"}
CAUSAL_PHRASES = ("caused", "causes", "cause of", "root cause", "because of", "due to", "will fail", "will break", "leads to")


@dataclass
class Check:
    status: str  # PASS, WARN, FAIL or SKIP
    name: str
    detail: str = ""


def _result(name: str, errors: list[str], ok_detail: str = "", warn: bool = False) -> Check:
    if not errors:
        return Check("PASS", name, ok_detail)
    shown = "; ".join(errors[:3]) + (f" (+{len(errors) - 3} more)" if len(errors) > 3 else "")
    return Check("WARN" if warn else "FAIL", name, shown)


def _order(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(["risk_percentile", "segment_id"], ascending=[False, True])


# ------------------------------------------------------------------ contracts A, B and metrics


def check_contracts(a: pd.DataFrame, b: pd.DataFrame, metrics: dict) -> list[Check]:
    checks = []
    report = validate_pipe_year(a)
    checks.append(_result("Contract A valid", report.errors, f"{len(a):,} rows"))
    checks.append(_result("Contract B valid", validate_fold_predictions(b), f"{len(b):,} rows"))
    checks.append(_result("metrics.json structure", validate_metrics(metrics)))
    checks.append(_result("metrics.json reproduces Contract B counts", metrics_consistency_errors(b, metrics),
                          "every year x budget x method"))
    checks.append(_result("Results are real, not synthetic",
                          ["metrics.json is flagged is_synthetic"] if metrics.get("is_synthetic") else []))
    complete = metrics.get("inputs", {}).get("outcomes_complete_through")
    late = [y for y in metrics.get("test_years", []) if complete is not None and y > complete]
    checks.append(_result("Test years have complete outcomes", [f"{late} after {complete}"] if late else [],
                          f"complete through {complete}"))
    checks.append(_result("Test years are the agreed 2023-2025", [] if metrics.get("test_years") == AGREED_TEST_YEARS
                          else [f"metrics.json has {metrics.get('test_years')}"], warn=True))
    methods = {k: v for k, v in metrics.get("methods", {}).items() if k != "champion"}
    try:
        expected = select_champion(methods)
        errors = [] if expected == metrics.get("champion_method") else [f"rule picks {expected}, file says {metrics.get('champion_method')}"]
    except ValueError as exc:
        errors = [str(exc)]
    checks.append(_result("Champion matches the selection rule", errors, str(metrics.get("champion_method"))))
    return checks


def check_join_a_b(a: pd.DataFrame, b: pd.DataFrame) -> list[Check]:
    """Every Contract B row must join to Contract A with the same length and outcome."""
    keyed = a.assign(segment_id=a["segment_id"].astype(str)).set_index(["segment_id", "score_year"])
    rows = b.drop_duplicates(["segment_id", "test_year"])
    index = pd.MultiIndex.from_arrays([rows["segment_id"].astype(str), rows["test_year"].astype(int)])
    present = index.isin(keyed.index)
    errors = []
    if not present.all():
        errors.append(f"{int((~present).sum())} Contract B segment-years missing from Contract A")
    joined = keyed.reindex(index[present])
    matched = rows[present]
    if not np.allclose(joined["length_m"].to_numpy(float), matched["length_m"].to_numpy(float)):
        errors.append("length_m differs between Contract A and B")
    if not (joined[TARGET].to_numpy(int) == matched["actual_break"].to_numpy(int)).all():
        errors.append("actual_break differs from Contract A target_next_year_break")
    return [_result("Contract A <-> B join (segment_id, year)", errors, f"{int(present.sum()):,} segment-years")]


# ------------------------------------------------------------------ contract C


def contract_c_errors(c: pd.DataFrame, b: pd.DataFrame, metrics: dict) -> dict[str, list[str]]:
    """Plan section 4 decision tests for Contract C, grouped by check name."""
    out: dict[str, list[str]] = {}
    missing = [col for col in CONTRACT_C_COLUMNS if col not in c.columns]
    out["Contract C columns"] = [f"missing {missing}"] if missing else []
    if missing:
        return out
    out["Contract C vocabularies"] = (
        [f"ranking_mode {sorted(set(c['ranking_mode']) - RANKING_MODES)}"] if set(c["ranking_mode"]) - RANKING_MODES else []
    ) + ([f"recommended_action {sorted(set(c['recommended_action']) - ACTIONS)}"] if set(c["recommended_action"]) - ACTIONS else [])

    validated = c.loc[c["ranking_mode"] == "VALIDATED_RISK"].assign(segment_id=lambda f: f["segment_id"].astype(str))
    order_errors, count_errors = [], []
    for (year, method), group in validated.groupby(["test_year", "method"]):
        source = _order(b.loc[(b["test_year"] == year) & (b["method"] == method)])
        ranked = group.sort_values("priority_rank")
        if ranked["segment_id"].tolist() != source["segment_id"].astype(str).tolist():
            order_errors.append(f"{year} {method}: order or candidate set differs from Contract B")
            continue
        if ranked["priority_rank"].tolist() != list(range(1, len(ranked) + 1)):
            order_errors.append(f"{year} {method}: priority_rank is not 1..n")
        lengths = source["length_m"].to_numpy(float)
        if not np.allclose(ranked["cumulative_length_m"].to_numpy(float), np.cumsum(lengths), atol=0.01):
            order_errors.append(f"{year} {method}: cumulative_length_m is not the running sum of Contract B lengths")
        for budget in metrics.get("budgets", []):
            cell = metrics.get("by_year", {}).get(str(year), {}).get(budget_label(budget), {}).get(method)
            if cell is None:
                continue
            chosen = ranked.loc[ranked["cumulative_length_m"].to_numpy(float) <= budget * math.fsum(lengths)]
            captured = int(chosen["actual_break"].sum())
            if len(chosen) != cell["selected_segments"] or captured != cell["breaks_captured"]:
                count_errors.append(f"{year} {budget_label(budget)} {method}: {len(chosen)}/{captured} vs metrics.json "
                                    f"{cell['selected_segments']}/{cell['breaks_captured']}")
    out["VALIDATED_RISK order equals Contract B"] = order_errors
    out["Contract C Proof Mode counts equal metrics.json"] = count_errors
    out["Contract C has baseline rows"] = [] if {"champion", "oldest"} <= set(validated["method"]) else [
        f"VALIDATED_RISK methods are {sorted(set(validated['method']))}; champion and oldest are needed for Proof Mode"]

    flags = b[["segment_id", "test_year", "method", "is_ood"]].assign(segment_id=lambda f: f["segment_id"].astype(str))
    joined = c.assign(segment_id=c["segment_id"].astype(str)).merge(flags, on=["segment_id", "test_year", "method"], how="left")
    unsafe = joined["recommended_action"].eq("RENEWAL_REVIEW") & (
        joined["confidence_label"].eq("LOW") | joined["is_ood"].fillna(False).astype(bool)
    )
    out["LOW/OOD never get RENEWAL_REVIEW"] = [f"{int(unsafe.sum())} rows"] if unsafe.any() else []
    text = (c["risk_pattern"].astype(str) + " " + c["reason_short"].astype(str)).str.lower()
    causal = [p for p in CAUSAL_PHRASES if text.str.contains(p, regex=False).any()]
    out["Risk patterns and reasons avoid causal language"] = [f"found {causal}"] if causal else []
    return out


def check_contract_c(path: Path, b: pd.DataFrame, metrics: dict) -> list[Check]:
    if not path.exists():
        return [Check("SKIP", "Contract C (ranked_worklists)", f"{path.name} not published yet (Member 3)")]
    c = pd.read_parquet(path)
    return [_result(name, errors, warn=name == "Contract C has baseline rows") for name, errors in contract_c_errors(c, b, metrics).items()]


# ------------------------------------------------------------------ app


def check_app(repo: Path, b: pd.DataFrame) -> list[Check]:
    app_dir = repo / "JagaPaip"
    if not (app_dir / "jagapaip" / "loader.py").exists():
        return [Check("SKIP", "App checks", "JagaPaip/ not found")]
    sys.path.insert(0, str(app_dir))
    try:
        from jagapaip.contract_proof import contract_budgets, contract_plans, contract_years, plan_mismatches
        from jagapaip.loader import ROOT, load_dataset
        from jagapaip.proof import features_for_year
        from jagapaip.ranking import build_worklist
        from jagapaip.schema import ACTION_INSPECT, ACTION_MONITOR, ACTION_PENDING, ACTION_RENEWAL
    except ImportError as exc:
        return [Check("FAIL", "App imports", str(exc))]
    finally:
        sys.path.remove(str(app_dir))

    data = load_dataset(ROOT)
    meta = data["meta"]
    checks = [_result("App runs in contract mode", [] if meta.get("contract_mode") else ["contract_mode is off"])]
    stale = [k for k, v in meta["files"].items() if v and str(app_dir / "data") in v]
    checks.append(_result("App reads the repo's live files", [f"copies in JagaPaip/data: {stale}"] if stale else []))
    if not meta.get("contract_mode"):
        return checks
    metrics, contract_b = data["metrics"], data["contract_b"]
    mismatches = [f"{y} {bud}: {p}" for y in contract_years(metrics) for bud in contract_budgets(metrics)
                  for p in plan_mismatches(contract_plans(contract_b, y, bud), metrics, y, bud, revealed=True)]
    checks.append(_result("App Proof Mode reproduces metrics.json", mismatches, "every year x budget"))
    year = int(meta["decision_year"])
    features = features_for_year(data, year)
    plan = build_worklist(features, budget_m=float(features["length_m"].sum()))
    expected = _order(b.loc[(b["test_year"] == year) & (b["method"] == "champion")])["segment_id"].astype(str).tolist()
    checks.append(_result("App worklist order equals Contract B champion", [] if plan["pipe_id"].tolist() == expected
                          else [f"{year}: order differs"], f"{len(expected):,} pipes, {year}"))
    known = {ACTION_RENEWAL, ACTION_INSPECT, ACTION_MONITOR, ACTION_PENDING}
    unknown = sorted(set(plan["recommended_action"]) - known)
    checks.append(_result("App understands every recommended action", [f"unknown {unknown}"] if unknown else [],
                          ", ".join(sorted(set(plan["recommended_action"])))))
    return checks


# ------------------------------------------------------------------ optional


def check_reproducible(repo: Path, b: pd.DataFrame, metrics: dict) -> list[Check]:
    """Rebuild Contract B and metrics.json from Member 1's package and compare."""
    from .adapters import load_member1_package
    from .evaluate import run_evaluation

    result = run_evaluation(load_member1_package(repo / "data"))
    errors = []
    try:
        pd.testing.assert_frame_equal(result.contract_b.reset_index(drop=True), b.reset_index(drop=True), check_dtype=False)
    except AssertionError as exc:
        errors.append(f"Contract B differs: {str(exc).splitlines()[0]}")
    fresh = json.loads(json.dumps(result.metrics))
    if {k: v for k, v in fresh.items() if k != "generated_at"} != {k: v for k, v in metrics.items() if k != "generated_at"}:
        errors.append("metrics.json differs from a fresh run")
    return [_result("Artifacts reproduce from data/ (fixed seed)", errors)]


def check_test_suites(repo: Path) -> list[Check]:
    checks = []
    for name, cwd, target in (("Modeling + decision tests", repo, "tests"), ("App tests", repo / "JagaPaip", "tests")):
        run = subprocess.run([sys.executable, "-m", "pytest", target, "-q", "-p", "no:cacheprovider"],
                             cwd=cwd, capture_output=True, text=True)
        last = (run.stdout.strip().splitlines() or ["no output"])[-1]
        checks.append(Check("PASS" if run.returncode == 0 else "FAIL", name, last))
    return checks


# ------------------------------------------------------------------ CLI


def run(artifacts: Path, repo: Path = REPO, app: bool = True, reproduce: bool = False, run_tests: bool = False) -> list[Check]:
    a = pd.read_parquet(artifacts / "pipe_year.parquet")
    b = pd.read_parquet(artifacts / "fold_predictions.parquet")
    metrics = json.loads((artifacts / "metrics.json").read_text(encoding="utf-8"))
    checks = check_contracts(a, b, metrics) + check_join_a_b(a, b)
    checks += check_contract_c(artifacts / "ranked_worklists.parquet", b, metrics)
    if app:
        checks += check_app(repo, b)
    if reproduce:
        checks += check_reproducible(repo, b, metrics)
    if run_tests:
        checks += check_test_suites(repo)
    return checks


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Integration smoke test for the team gates")
    parser.add_argument("--artifacts", type=Path, default=REPO / "artifacts")
    parser.add_argument("--no-app", action="store_true", help="skip the Streamlit app checks")
    parser.add_argument("--reproduce", action="store_true", help="rebuild B + metrics.json from data/ and compare")
    parser.add_argument("--run-tests", action="store_true", help="also run every lane's pytest suite")
    args = parser.parse_args(argv)

    checks = run(args.artifacts, app=not args.no_app, reproduce=args.reproduce, run_tests=args.run_tests)
    for check in checks:
        print(f"{check.status:<5} {check.name}" + (f"  -  {check.detail}" if check.detail else ""))
    counts = {s: sum(c.status == s for c in checks) for s in ("PASS", "WARN", "FAIL", "SKIP")}
    print("\n" + ", ".join(f"{n} {s.lower()}" for s, n in counts.items()))
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
