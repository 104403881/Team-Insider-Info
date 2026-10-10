"""Contract validators owned or consumed by the modeling lane.

* Contract A (consumer check): what Member 1's pipe_year must pass before
  modeling runs. Column rules mirror TEAM_EXECUTION_PLAN.md section 4.
* Contract B (producer): fold_predictions, driven by
  contracts/fold_predictions.schema.json so the schema and code cannot drift.
* metrics.json (producer) and its exact consistency with Contract B.

Every validator returns a list of human-readable errors; empty means valid.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.api import types as ptypes

from .budget import evaluate_budget
from .config import CONTRACT_METHODS, PRIMARY_BUDGET, SCHEMA_VERSION, TARGET, budget_key, budget_label
from .features import numeric

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"

CONTRACT_A_COLUMNS = [
    {"name": "segment_id", "type": "string"},
    {"name": "score_year", "type": "integer"},
    {"name": "install_year", "type": "integer", "nullable": True},
    {"name": "age_years", "type": "float", "nullable": True},
    {"name": "material", "type": "string"},
    {"name": "diameter_mm", "type": "float", "nullable": True},
    {"name": "length_m", "type": "float", "exclusiveMinimum": 0},
    {"name": "prior_break_count", "type": "integer", "minimum": 0},
    {"name": "years_since_last_break", "type": "float", "nullable": True, "minimum": 0},
    {"name": "nearby_prior_breaks", "type": "integer", "nullable": True, "required": False, "minimum": 0},
    {"name": "is_ambiguous_history", "type": "boolean"},
    {"name": "data_quality_flags", "type": "string"},
    {"name": "geometry_wkt", "type": "string", "nullable": True, "required": False},
    {"name": TARGET, "type": "integer", "enum": [0, 1]},
    {"name": "source_snapshot_date", "type": "date_or_string"},
]
# Current condition scores are influenced by later failures, so they leak.
FORBIDDEN_COLUMN_SUBSTRINGS = ("condition",)

REQUIRED_METRICS_KEYS = (
    "schema_version",
    "generated_at",
    "data_snapshot",
    "selection_unit",
    "champion_method",
    "champion_selection_rule",
    "test_years",
    "budgets",
    "methods",
    "by_year",
    "limitations",
)


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_schema(name: str) -> dict:
    with open(CONTRACTS_DIR / f"{name}.schema.json", encoding="utf-8") as fh:
        return json.load(fh)


def _integral_floats(series: pd.Series) -> bool:
    if not ptypes.is_float_dtype(series):
        return False
    values = series.dropna().to_numpy(dtype=float)
    return bool(np.all(np.mod(values, 1) == 0))


def _type_ok(series: pd.Series, expected: str, lenient_integers: bool) -> bool:
    if expected == "string":
        return ptypes.infer_dtype(series, skipna=True) in ("string", "empty")
    if expected == "integer":
        strict = ptypes.is_integer_dtype(series) and not ptypes.is_bool_dtype(series)
        return strict or (lenient_integers and _integral_floats(series))
    if expected == "float":
        return ptypes.is_numeric_dtype(series) and not ptypes.is_bool_dtype(series)
    if expected == "boolean":
        return ptypes.is_bool_dtype(series)
    if expected == "date_or_string":
        return ptypes.infer_dtype(series, skipna=True) in (
            "string", "date", "datetime", "datetime64", "empty"
        )
    raise ValueError(f"unknown column type {expected!r}")


def _validate_columns(df: pd.DataFrame, columns: list[dict], lenient_integers: bool = False) -> list[str]:
    errors = []
    for col in columns:
        name = col["name"]
        if name not in df.columns:
            if col.get("required", True):
                errors.append(f"missing required column {name!r}")
            continue
        series = df[name]
        if not _type_ok(series, col["type"], lenient_integers):
            errors.append(f"{name}: expected {col['type']}, found dtype {series.dtype}")
        nulls = int(series.isna().sum())
        if nulls and not col.get("nullable", False):
            errors.append(f"{name}: {nulls} null values in a non-nullable column")
        values = series.dropna()
        if "enum" in col:
            bad = sorted(set(values.unique()) - set(col["enum"]), key=str)
            if bad:
                errors.append(f"{name}: values outside {col['enum']}: {bad[:5]}")
        as_number = numeric(values) if col["type"] in ("integer", "float") else None
        if as_number is not None:
            if "minimum" in col and (n := int((as_number < col["minimum"]).sum())):
                errors.append(f"{name}: {n} values below minimum {col['minimum']}")
            if "maximum" in col and (n := int((as_number > col["maximum"]).sum())):
                errors.append(f"{name}: {n} values above maximum {col['maximum']}")
            if "exclusiveMinimum" in col and (n := int((as_number <= col["exclusiveMinimum"]).sum())):
                errors.append(f"{name}: {n} values must be > {col['exclusiveMinimum']}")
    return errors


def _missing_columns(errors: list[str]) -> bool:
    return any(e.startswith("missing required column") for e in errors)


def validate_pipe_year(df: pd.DataFrame) -> ValidationReport:
    """Consumer acceptance check for Contract A (Member 1's pipe_year)."""
    report = ValidationReport(_validate_columns(df, CONTRACT_A_COLUMNS, lenient_integers=True))
    forbidden = [c for c in df.columns if any(s in c.lower() for s in FORBIDDEN_COLUMN_SUBSTRINGS)]
    if forbidden:
        report.errors.append(f"forbidden post-outcome columns present: {forbidden}")
    if _missing_columns(report.errors):
        return report

    duplicates = int(df.duplicated(["segment_id", "score_year"]).sum())
    if duplicates:
        report.errors.append(f"{duplicates} duplicate rows on key (segment_id, score_year)")

    age = numeric(df["age_years"])
    ambiguous = df["is_ambiguous_history"].astype(bool)
    if n := int(((age < 0) & ~ambiguous).sum()):
        report.errors.append(
            f"{n} rows have negative age_years but are not flagged is_ambiguous_history"
        )
    expected_age = numeric(df["score_year"]) - numeric(df["install_year"])
    if n := int(((age - expected_age).abs() > 1e-6).sum()):
        report.errors.append(f"{n} rows where age_years != score_year - install_year")

    flags = pd.Series(df["data_quality_flags"].dropna().unique())
    if n := int((~flags.map(_is_json_list)).sum()):
        report.errors.append(f"data_quality_flags: {n} distinct values are not JSON arrays")

    prior = numeric(df["prior_break_count"])
    since_last = numeric(df["years_since_last_break"])
    if n := int(((prior == 0) & since_last.notna()).sum()):
        report.warnings.append(f"{n} rows have years_since_last_break but no prior breaks")
    if n := int(((prior > 0) & since_last.isna()).sum()):
        report.warnings.append(f"{n} rows have prior breaks but no years_since_last_break")
    for col in CONTRACT_A_COLUMNS:
        if col["type"] == "integer" and col["name"] in df and ptypes.is_float_dtype(df[col["name"]]):
            report.warnings.append(f"{col['name']} is stored as float; nullable Int64 is preferred")
    return report


def _is_json_list(text) -> bool:
    try:
        return isinstance(json.loads(text), list)
    except (TypeError, ValueError):
        return False


def validate_fold_predictions(df: pd.DataFrame, schema: dict | None = None) -> list[str]:
    """Producer check for Contract B against contracts/fold_predictions.schema.json."""
    schema = schema or load_schema("fold_predictions")
    errors = _validate_columns(df, schema["columns"])
    if _missing_columns(errors):
        return errors

    key = schema["primary_key"]
    if duplicates := int(df.duplicated(key).sum()):
        errors.append(f"{duplicates} duplicate rows on primary key {key}")

    required_methods = next(c["enum"] for c in schema["columns"] if c["name"] == "method")
    for year, rows in df.groupby("test_year"):
        missing = [m for m in required_methods if m not in set(rows["method"])]
        if missing:
            errors.append(f"test_year {year}: missing methods {missing}")
        segment_sets = {frozenset(g["segment_id"]) for _, g in rows.groupby("method")}
        if len(segment_sets) > 1:
            errors.append(
                f"test_year {year}: methods rank different segment sets, "
                "so their length budgets would differ"
            )
        per_segment = rows.groupby("segment_id")[["actual_break", "length_m"]].nunique()
        if (per_segment > 1).to_numpy().any():
            errors.append(
                f"test_year {year}: actual_break or length_m differs between methods "
                "for the same segment"
            )
    return errors


def validate_metrics(metrics: dict) -> list[str]:
    """Producer check for metrics.json structure (values are checked separately)."""
    errors = [f"metrics.json missing key {k!r}" for k in REQUIRED_METRICS_KEYS if k not in metrics]
    if errors:
        return errors
    if metrics["schema_version"] != SCHEMA_VERSION:
        errors.append(f"schema_version {metrics['schema_version']!r} != {SCHEMA_VERSION!r}")
    try:
        json.dumps(metrics, allow_nan=False)
    except ValueError as exc:
        errors.append(f"metrics.json is not strict JSON: {exc}")

    primary = budget_key(PRIMARY_BUDGET)
    methods = metrics["methods"]
    for method in (*CONTRACT_METHODS, metrics["champion_method"]):
        if method not in methods:
            errors.append(f"methods is missing {method!r}")
            continue
        for name in (f"capture_at_{primary}", f"precision_at_{primary}", f"observed_non_events_at_{primary}"):
            if name not in methods[method]:
                errors.append(f"methods.{method} is missing {name!r}")
    for method, entry in methods.items():
        for name, value in entry.items():
            is_rate = name.startswith(("capture_at_", "precision_at_")) and not name.endswith("_std")
            if is_rate and value is not None and not 0 <= value <= 1:
                errors.append(f"methods.{method}.{name} = {value} is outside [0, 1]")

    for year in metrics["test_years"]:
        year_entry = metrics["by_year"].get(str(year))
        if year_entry is None:
            errors.append(f"by_year is missing {year}")
            continue
        for budget in metrics["budgets"]:
            cell = year_entry.get(budget_label(budget), {}).get("champion")
            if cell is None:
                errors.append(f"by_year.{year}.{budget_label(budget)} has no champion entry")
                continue
            for name in ("selected_length_m", "breaks_captured", "capture"):
                if name not in cell:
                    errors.append(f"by_year.{year}.{budget_label(budget)}.champion is missing {name!r}")
    return errors


def metrics_consistency_errors(contract_b: pd.DataFrame, metrics: dict) -> list[str]:
    """Recompute every per-year count from Contract B and compare with metrics.json.

    Counts must match exactly; this is the check behind "Proof Mode counters
    match Contract B and metrics.json".
    """
    errors = []
    for (year, method), group in contract_b.groupby(["test_year", "method"]):
        for budget in metrics["budgets"]:
            label = budget_label(budget)
            expected = metrics["by_year"].get(str(year), {}).get(label, {}).get(method)
            if expected is None:
                errors.append(f"metrics.json has no by_year.{year}.{label}.{method}")
                continue
            outcome = evaluate_budget(group, budget)
            for name in ("breaks_captured", "selected_segments", "total_breaks"):
                if name in expected and getattr(outcome, name) != expected[name]:
                    errors.append(
                        f"{year} {label} {method}: {name} {getattr(outcome, name)} "
                        f"!= metrics.json {expected[name]}"
                    )
            if not math.isclose(outcome.selected_length_m, expected["selected_length_m"], abs_tol=1e-2):
                errors.append(
                    f"{year} {label} {method}: selected_length_m {outcome.selected_length_m:.3f} "
                    f"!= metrics.json {expected['selected_length_m']}"
                )
    return errors
