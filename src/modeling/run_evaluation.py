"""Command-line entry point for the modeling lane (run from the repo root).

Real data:
    python -m src.modeling.run_evaluation --input artifacts/pipe_year.parquet

Contract B fixture for Members 3 and 4 (synthetic, clearly flagged):
    python -m src.modeling.run_evaluation --synthetic \
        --predictions-out contracts/fixtures/fold_predictions.fixture.parquet \
        --metrics-out contracts/fixtures/metrics.example.json \
        --write-synthetic-input artifacts/dev/pipe_year.synthetic.parquet

Nothing is written unless Contract A, Contract B and metrics.json all validate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from .config import BOOTSTRAP_RESAMPLES, PRIMARY_BUDGET, SEED, budget_key, budget_label
from .contracts import (
    metrics_consistency_errors,
    validate_fold_predictions,
    validate_metrics,
    validate_pipe_year,
)
from .evaluate import run_evaluation
from .synthetic import DEFAULT_SEGMENTS, make_synthetic_pipe_year


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Walk-forward evaluation: Contract A -> Contract B + metrics.json")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Contract A parquet (pipe_year)")
    source.add_argument("--synthetic", action="store_true", help="use generated development data")
    parser.add_argument("--synthetic-segments", type=int, default=DEFAULT_SEGMENTS)
    parser.add_argument("--synthetic-seed", type=int, default=7)
    parser.add_argument("--write-synthetic-input", type=Path, help="also save the synthetic Contract A used")
    parser.add_argument("--test-years", type=int, nargs="+", help="default: latest three with enough history")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--include-ambiguous", action="store_true", help="keep ambiguous histories in the primary panel")
    parser.add_argument("--no-sensitivity", action="store_true", help="skip the ambiguity sensitivity rerun")
    parser.add_argument("--bootstrap", type=int, default=BOOTSTRAP_RESAMPLES, help="bootstrap resamples; 0 skips")
    parser.add_argument("--no-stress", action="store_true", help="skip the missing/noisy-input stress tests")
    parser.add_argument("--predictions-out", type=Path, default=Path("artifacts/fold_predictions.parquet"))
    parser.add_argument("--metrics-out", type=Path, default=Path("artifacts/metrics.json"))
    return parser.parse_args(argv)


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _fmt(value, width: int = 9) -> str:
    return f"{'n/a':>{width}}" if value is None else f"{value:>{width}.3f}"


def print_summary(metrics: dict) -> None:
    if metrics["is_synthetic"]:
        print("SYNTHETIC DATA - the numbers below are not results.")
    print(f"Champion: {metrics['champion_method']}  ({metrics['champion_selection_rule']})")
    keys = [budget_key(b) for b in metrics["budgets"]]
    primary = budget_key(PRIMARY_BUDGET)
    print(
        f"{'method':<14}"
        + "".join(f"{'cap@' + k:>9}" for k in keys)
        + f"{'prec@' + primary:>9}{'non-ev@' + primary:>11}{'PR-AUC':>9}"
    )
    for method, entry in metrics["methods"].items():
        print(
            f"{method:<14}"
            + "".join(_fmt(entry.get(f"capture_at_{k}")) for k in keys)
            + _fmt(entry.get(f"precision_at_{primary}"))
            + f"{entry.get(f'observed_non_events_at_{primary}', ''):>11}"
            + _fmt(entry.get("pr_auc_mean"))
        )

    label = budget_label(PRIMARY_BUDGET)
    uncertainty = metrics.get("uncertainty", {})
    if "capture" in uncertainty:
        level = round(uncertainty["confidence_level"] * 100)
        print(f"\n{level}% bootstrap interval, capture@{primary} (mean across test years):")
        for method, block in uncertainty["capture"][label].items():
            print(f"  {method:<14}{_interval(block['ci_mean'])}")
        diff = uncertainty["difference_vs_oldest"][label].get("champion")
        if diff:
            print(
                f"  champion - oldest: {_interval(diff['ci_mean'])}; "
                f"above zero in {diff['share_of_resamples_above_zero']:.1%} of resamples"
            )

    robustness = metrics.get("robustness", {})
    if "scenarios" in robustness:
        print(f"\nStress tests (champion): change in capture@{primary}, rank correlation, LOW share of affected rows")
        for name, scenario in robustness["scenarios"].items():
            champ = scenario["methods"]["champion"]
            low = scenario["affected_rows_confidence"].get("LOW")
            print(
                f"  {name:<20}{_fmt(champ.get(f'capture_at_{primary}_change'))}"
                f"{_fmt(champ.get('spearman_rank_corr'))}{_fmt(low)}"
            )


def _interval(bounds) -> str:
    return "n/a" if not bounds else f"[{bounds[0]:.3f}, {bounds[1]:.3f}]"


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.synthetic:
        pipe_year = make_synthetic_pipe_year(n_segments=args.synthetic_segments, seed=args.synthetic_seed)
        if args.write_synthetic_input:
            _write_parquet(pipe_year, args.write_synthetic_input)
    else:
        pipe_year = pd.read_parquet(args.input)

    report = validate_pipe_year(pipe_year)
    for warning in report.warnings:
        print(f"WARNING (Contract A): {warning}", file=sys.stderr)
    if report.errors:
        for error in report.errors:
            print(f"ERROR (Contract A): {error}", file=sys.stderr)
        return 2

    try:
        result = run_evaluation(
            pipe_year,
            test_years=args.test_years,
            seed=args.seed,
            exclude_ambiguous=not args.include_ambiguous,
            run_sensitivity=not args.no_sensitivity,
            n_bootstrap=args.bootstrap,
            run_stress=not args.no_stress,
        )
    except ValueError as exc:  # e.g. an incomplete or unknown test year
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    errors = (
        validate_fold_predictions(result.contract_b)
        + validate_metrics(result.metrics)
        + metrics_consistency_errors(result.contract_b, result.metrics)
    )
    if errors:
        for error in errors:
            print(f"ERROR (outputs): {error}", file=sys.stderr)
        return 3

    _write_parquet(result.contract_b, args.predictions_out)
    args.metrics_out.parent.mkdir(parents=True, exist_ok=True)
    args.metrics_out.write_text(json.dumps(result.metrics, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    print_summary(result.metrics)
    print(f"Wrote {args.predictions_out} ({len(result.contract_b):,} rows) and {args.metrics_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
