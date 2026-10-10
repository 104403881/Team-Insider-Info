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

from .config import PRIMARY_BUDGET, SEED, budget_key
from .contracts import (
    metrics_consistency_errors,
    validate_fold_predictions,
    validate_metrics,
    validate_pipe_year,
)
from .evaluate import run_evaluation
from .synthetic import make_synthetic_pipe_year


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Walk-forward evaluation: Contract A -> Contract B + metrics.json")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Contract A parquet (pipe_year)")
    source.add_argument("--synthetic", action="store_true", help="use generated development data")
    parser.add_argument("--synthetic-segments", type=int, default=600)
    parser.add_argument("--synthetic-seed", type=int, default=7)
    parser.add_argument("--write-synthetic-input", type=Path, help="also save the synthetic Contract A used")
    parser.add_argument("--test-years", type=int, nargs="+", help="default: latest three with enough history")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--include-ambiguous", action="store_true", help="keep ambiguous histories in the primary panel")
    parser.add_argument("--no-sensitivity", action="store_true", help="skip the ambiguity sensitivity rerun")
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

    result = run_evaluation(
        pipe_year,
        test_years=args.test_years,
        seed=args.seed,
        exclude_ambiguous=not args.include_ambiguous,
        run_sensitivity=not args.no_sensitivity,
    )

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
