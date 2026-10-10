"""Load team artifacts when they exist, otherwise build the labelled demo set."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from jagapaip.demo_data import build_demo_tables
from jagapaip.schema import (
    BREAKS_CLEAN_FILE,
    DEMO_DECISION_YEAR,
    FEATURES_FILE,
    MANIFEST_FILE,
    METRICS_FILE,
    OUTCOMES_FILE,
    PIPE_COLUMN_ALIASES,
    PIPE_YEAR_FILE,
    PIPES_CLEAN_FILE,
    PREDICTION_COLUMN_ALIASES,
    PREDICTIONS_FILE,
    WORKLIST_FILE,
)

TEAM_FILES = (
    PIPE_YEAR_FILE,
    FEATURES_FILE,
    OUTCOMES_FILE,
    BREAKS_CLEAN_FILE,
    PIPES_CLEAN_FILE,
    PREDICTIONS_FILE,
    METRICS_FILE,
    WORKLIST_FILE,
    MANIFEST_FILE,
)

ROOT = Path(__file__).resolve().parent.parent


class DataSchemaError(ValueError):
    """A provided file is present but cannot be interpreted."""


def locate(root: Path, filename: str) -> Path | None:
    """Find a team artifact by name, including a csv twin and common folders."""
    names = [filename]
    suffix = Path(filename).suffix.lower()
    stem = Path(filename).stem
    if suffix == ".parquet":
        names.append(f"{stem}.csv")
    folders = (root / "data", root, root / "artifacts", root / "outputs")
    for folder in folders:
        for name in names:
            candidate = folder / name
            if candidate.is_file():
                return candidate
    return None


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_parquet(path)


def file_signature(root: Path | None = None) -> tuple:
    """Modification stamps so the app reloads when a teammate drops in a file."""
    root = root or ROOT
    signature = []
    for filename in TEAM_FILES:
        path = locate(root, filename)
        if path is None:
            signature.append((filename, None, None))
        else:
            stat = path.stat()
            signature.append((filename, stat.st_mtime, stat.st_size))
    return tuple(signature)


def canonicalise(frame: pd.DataFrame, aliases: dict[str, list[str]]) -> pd.DataFrame:
    renamed = frame.copy()
    renamed.columns = [str(column).strip().lower() for column in renamed.columns]
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for canonical, names in aliases.items():
        for name in names:
            if name in renamed.columns and name not in used:
                mapping[name] = canonical
                used.add(name)
                break
    return renamed.rename(columns=mapping)


def _coerce_number(frame: pd.DataFrame, column: str) -> None:
    if column in frame.columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")


def _event_ledger(table: pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    """Turn a pipe-year break column into one row per recorded break event.

    Counts that never fall as the year increases are treated as a running total,
    and the ledger stores the increase. Any decrease is treated as events in that year.
    """
    rows: list[tuple[str, int, int]] = []
    cumulative_pipes = 0
    for pipe_id, group in table.groupby("pipe_id", sort=False):
        ordered = group.dropna(subset=["year"]).sort_values("year")
        counts = pd.to_numeric(ordered["break_count"], errors="coerce")
        valid = counts.dropna()
        cumulative = False
        if len(valid) >= 3:
            cumulative = bool((valid.diff().dropna() >= -1e-6).all())
        if cumulative:
            cumulative_pipes += 1
            previous = 0.0
            for year, total in zip(ordered["year"], counts, strict=False):
                if pd.isna(total):
                    continue
                increment = max(float(total) - previous, 0.0)
                previous = float(total)
                if increment > 0:
                    rows.append((str(pipe_id), int(year), int(round(increment))))
        else:
            for year, total in zip(ordered["year"], counts, strict=False):
                if pd.isna(total) or float(total) <= 0:
                    continue
                rows.append((str(pipe_id), int(year), int(round(float(total)))))
    note = None
    if cumulative_pipes:
        note = (
            f"Break counts for {cumulative_pipes} pipes never fell as the year increased, "
            "so they were read as running totals. The ledger stores the increase between years."
        )
    if not rows:
        return pd.DataFrame(columns=["pipe_id", "break_year", "break_count"]), note
    return pd.DataFrame(rows, columns=["pipe_id", "break_year", "break_count"]), note


def interpret_pipe_table(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame | None, list[str], int | None]:
    """Split a pipe or pipe-year table into attributes and an optional break ledger."""
    warnings: list[str] = []
    table = canonicalise(frame, PIPE_COLUMN_ALIASES)
    if "pipe_id" not in table.columns:
        raise DataSchemaError("No pipe identifier column was found. Expected one of: pipe_id, segment_id, asset_id, id.")
    if "length_m" not in table.columns:
        raise DataSchemaError("No length column was found. Expected length_m or length, in metres.")

    table["pipe_id"] = table["pipe_id"].astype(str)
    for column in ("length_m", "install_year", "diameter_mm", "break_count", "year", "cost"):
        _coerce_number(table, column)

    has_year = "year" in table.columns and table["year"].notna().any()
    has_breaks = "break_count" in table.columns
    snapshot_year = int(table["year"].max()) if has_year else None

    if has_year:
        table = table.sort_values(["pipe_id", "year"])
        attribute_columns = [
            column
            for column in ("material", "install_year", "length_m", "diameter_mm", "zone", "cost", "prior_break_count")
            if column in table.columns
        ]

        def _last_valid(series: pd.Series):
            valid = series.dropna()
            if valid.empty:
                return pd.NA
            return valid.iloc[-1]

        pipes = table.groupby("pipe_id", as_index=False)[attribute_columns].agg(_last_valid)
        if has_breaks:
            ledger, ledger_note = _event_ledger(table)
            if ledger_note:
                warnings.append(ledger_note)
        else:
            ledger = None
            if "prior_break_count" not in table.columns:
                warnings.append("The pipe-year file has no break-count column, so Proof Mode cannot compare outcomes.")
    else:
        pipes = table.drop_duplicates("pipe_id").copy()
        ledger = None
        if has_breaks:
            pipes["historical_breaks"] = pd.to_numeric(pipes["break_count"], errors="coerce")
            warnings.append(
                "Breaks are a single total per pipe, with no year. Proof Mode cannot hold out a future window."
            )
        else:
            warnings.append("No break history was found in the pipe file.")

    before = len(pipes)
    pipes = pipes.loc[pipes["length_m"].notna() & (pipes["length_m"] > 0)].copy()
    dropped = before - len(pipes)
    if dropped:
        warnings.append(f"{dropped} segments were skipped because length was missing or not positive.")
    if "install_year" not in pipes.columns:
        warnings.append("Install year is missing, so age and the oldest-first baseline are unavailable.")
        pipes["install_year"] = pd.NA
    if "material" not in pipes.columns:
        pipes["material"] = "Unknown"
        warnings.append("Material is missing. Unknown material uses a neutral screening weight.")
    if "zone" not in pipes.columns:
        pipes["zone"] = "Not recorded"
    if "diameter_mm" not in pipes.columns:
        pipes["diameter_mm"] = pd.NA
    if "prior_break_count" in pipes.columns and "historical_breaks" not in pipes.columns:
        pipes["historical_breaks"] = pd.to_numeric(pipes["prior_break_count"], errors="coerce")

    pipes["length_m"] = pipes["length_m"].astype(float)
    if "cost" in pipes.columns and pd.to_numeric(pipes["cost"], errors="coerce").notna().any():
        warnings.append(
            "A cost column was found. The worklist can allocate by those supplied units. They were not converted to a currency."
        )
    ledger_out = None if ledger is None else ledger.reset_index(drop=True)
    return pipes.reset_index(drop=True), ledger_out, warnings, snapshot_year


def interpret_break_events(frame: pd.DataFrame) -> pd.DataFrame | None:
    """Read a dated incident table (breaks_clean) into the Proof Mode ledger."""
    table = canonicalise(frame, {
        "pipe_id": PIPE_COLUMN_ALIASES["pipe_id"],
        "break_year": ["break_year", "incident_year", "year"],
        "break_count": ["break_count", "incident_count"],
    })
    if "pipe_id" not in table.columns or "break_year" not in table.columns:
        return None
    table["pipe_id"] = table["pipe_id"].astype(str)
    table["break_year"] = pd.to_numeric(table["break_year"], errors="coerce")
    table = table.loc[table["break_year"].notna()].copy()
    if table.empty:
        return pd.DataFrame(columns=["pipe_id", "break_year", "break_count"])
    if "break_count" not in table.columns:
        table["break_count"] = 1
    table["break_count"] = pd.to_numeric(table["break_count"], errors="coerce").fillna(1)
    return table[["pipe_id", "break_year", "break_count"]].reset_index(drop=True)


def interpret_feature_panel(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Year-level features with outcome columns removed."""
    warnings: list[str] = []
    table = canonicalise(frame, PIPE_COLUMN_ALIASES)
    blocked = [column for column in table.columns if str(column).lower().startswith("target_") or str(column).lower() in {"outcome_coverage", "y_true", "label"}]
    if blocked:
        table = table.drop(columns=blocked)
        warnings.append("Outcome columns were removed from the feature panel and are not used to rank.")
    if "pipe_id" not in table.columns or "year" not in table.columns:
        raise DataSchemaError("A feature panel needs segment_id/pipe_id and year.")
    table["pipe_id"] = table["pipe_id"].astype(str)
    table["year"] = pd.to_numeric(table["year"], errors="coerce")
    table = table.loc[table["year"].notna() & table["length_m"].notna() & (table["length_m"] > 0)].copy()
    if "prior_break_count" in table.columns:
        table["historical_breaks"] = pd.to_numeric(table["prior_break_count"], errors="coerce")
    if "install_year" not in table.columns:
        table["install_year"] = pd.NA
    if "material" not in table.columns:
        table["material"] = "Unknown"
    if "zone" not in table.columns:
        table["zone"] = "Not recorded"
    if "diameter_mm" not in table.columns:
        table["diameter_mm"] = pd.NA
    return table.reset_index(drop=True), warnings


def interpret_predictions(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    table = canonicalise(frame, PREDICTION_COLUMN_ALIASES)
    if "pipe_id" not in table.columns or "predicted_risk" not in table.columns:
        raise DataSchemaError("fold_predictions needs a pipe id and a score column such as predicted_risk, y_pred, or probability.")
    keep = ["pipe_id", "predicted_risk"]
    table["pipe_id"] = table["pipe_id"].astype(str)
    table["predicted_risk"] = pd.to_numeric(table["predicted_risk"], errors="coerce")
    table = table.loc[table["predicted_risk"].notna()].copy()
    if "year" in table.columns:
        table["year"] = pd.to_numeric(table["year"], errors="coerce")
        keep.append("year")
    else:
        warnings.append("fold_predictions has no year column. The same score will be offered for every decision year.")
    if "fold" in table.columns:
        warnings.append("Several folds were found. JagaPaip averages predicted_risk within each pipe and year.")
    narrowed = table[keep]
    if "year" in narrowed.columns:
        averaged = narrowed.groupby(["pipe_id", "year"], dropna=False, as_index=False)["predicted_risk"].mean()
    else:
        averaged = narrowed.groupby("pipe_id", as_index=False)["predicted_risk"].mean()
    outside = averaged.loc[(averaged["predicted_risk"] < 0) | (averaged["predicted_risk"] > 1)]
    if len(outside):
        warnings.append(
            "Some supplied scores are outside 0 to 1. They are still used for ranking. "
            "Action bands at 0.45 and 0.70 may not match the scale of that file."
        )
    return averaged, warnings


def load_dataset(root: Path | None = None) -> dict:
    """Return pipes, optional ledgers, and a meta block describing the source."""
    root = Path(root) if root is not None else ROOT
    warnings: list[str] = []
    found = {
        "pipe_year": locate(root, PIPE_YEAR_FILE),
        "features": locate(root, FEATURES_FILE),
        "outcomes": locate(root, OUTCOMES_FILE),
        "breaks_clean": locate(root, BREAKS_CLEAN_FILE),
        "pipes_clean": locate(root, PIPES_CLEAN_FILE),
        "fold_predictions": locate(root, PREDICTIONS_FILE),
        "metrics": locate(root, METRICS_FILE),
        "ranked_worklists": locate(root, WORKLIST_FILE),
        "manifest": locate(root, MANIFEST_FILE),
    }

    pipes: pd.DataFrame | None = None
    breaks: pd.DataFrame | None = None
    snapshot_year: int | None = None
    if found["pipe_year"] is not None:
        try:
            raw = read_table(found["pipe_year"])
            pipes, breaks, pipe_warnings, snapshot_year = interpret_pipe_table(raw)
            warnings.extend(pipe_warnings)
        except Exception as exc:
            warnings.append(
                f"{PIPE_YEAR_FILE} was found but could not be used ({exc}). Demo data is shown so the interface stays available."
            )
            pipes = None
            breaks = None

    panel = None
    if found["features"] is not None:
        try:
            panel, panel_warnings = interpret_feature_panel(read_table(found["features"]))
            warnings.extend(panel_warnings)
        except Exception as exc:
            warnings.append(f"{FEATURES_FILE} was found but could not be used ({exc}).")
            panel = None
    elif pipes is not None and found["pipe_year"] is not None:
        try:
            panel, panel_warnings = interpret_feature_panel(read_table(found["pipe_year"]))
            warnings.extend(panel_warnings)
        except Exception:
            panel = None

    if found["breaks_clean"] is not None:
        try:
            dated = interpret_break_events(read_table(found["breaks_clean"]))
            if dated is not None and not dated.empty:
                breaks = dated
        except Exception as exc:
            warnings.append(f"{BREAKS_CLEAN_FILE} was found but could not be used ({exc}).")

    manifest = None
    if found["manifest"] is not None:
        try:
            manifest = json.loads(found["manifest"].read_text(encoding="utf-8"))
        except Exception as exc:
            warnings.append(f"{MANIFEST_FILE} was found but could not be read ({exc}).")
            manifest = None

    predictions = None
    if found["fold_predictions"] is not None:
        try:
            raw_predictions = read_table(found["fold_predictions"])
            predictions, prediction_warnings = interpret_predictions(raw_predictions)
            warnings.extend(prediction_warnings)
        except Exception as exc:
            warnings.append(f"{PREDICTIONS_FILE} was found but could not be used ({exc}).")
            predictions = None

    metrics = None
    if found["metrics"] is not None:
        try:
            metrics = json.loads(found["metrics"].read_text(encoding="utf-8"))
        except Exception as exc:
            warnings.append(f"{METRICS_FILE} was found but could not be read ({exc}).")
            metrics = None

    worklists = None
    if found["ranked_worklists"] is not None:
        try:
            worklists = read_table(found["ranked_worklists"])
        except Exception as exc:
            warnings.append(f"{WORKLIST_FILE} was found but could not be read ({exc}).")
            worklists = None

    if pipes is not None and pipes.empty:
        warnings.append("The pipe file produced no segments with a positive length. Demo data is shown instead.")
        pipes = None
        breaks = None

    if pipes is None:
        pipes, breaks = build_demo_tables()
        panel = None
        mode = "demo"
        decision_year = DEMO_DECISION_YEAR
        status_title = "DEMO DATA — NOT REAL UTILITY DATA"
        status_detail = (
            "No usable pipe_year file is loaded. This network is synthetic and exists so the interface can be demonstrated."
        )
        length_note = "Lengths are generated in metres."
        score_note = (
            "Scores are a screening heuristic based on age, material, and recorded breaks. "
            "They are not a probability and they are not a validated model."
        )
    else:
        mode = "artifacts"
        if snapshot_year is not None:
            decision_year = snapshot_year
        elif breaks is not None and not breaks.empty:
            decision_year = int(breaks["break_year"].max())
        else:
            decision_year = DEMO_DECISION_YEAR
            warnings.append(
                f"No observation year was available. Ages use decision year {DEMO_DECISION_YEAR} until the file provides one."
            )
        member1 = found["features"] is not None and found["breaks_clean"] is not None
        kitchener = member1 or bool(manifest and "kitchener" in json.dumps(manifest).lower())
        status_title = (
            "Kitchener open data — method demonstrator"
            if kitchener
            else f"Loaded {found['pipe_year'].name}"
        )
        status_detail = (
            "City of Kitchener water-main inventory and completed main-break records. "
            "This is a method demonstrator. It does not establish effectiveness for Malaysian utilities."
            if kitchener
            else "Figures below come from the file in this project. They are only as complete as that file."
        )
        length_note = "Length is projected metres from the team inventory (length_m)."
        if predictions is not None:
            score_note = "Risk scores come from fold_predictions where a value exists for the decision year. Missing scores use the screening heuristic."
        else:
            score_note = (
                "No fold_predictions file was in the handoff. Risk scores are the screening heuristic, "
                "not Member 2 model scores and not a validated probability."
            )
        warnings.append(
            "Member 1 handoff: no trained model and no metrics.json. Ranking uses age, material, and prior breaks only. "
            "target_next_year_break and target_break_count are held out of ranking."
        )

    if mode == "demo" and metrics is not None:
        warnings.append("metrics.json is loaded, but it does not describe the synthetic network on the other pages.")
    if mode == "demo" and worklists is not None:
        warnings.append("ranked_worklists.parquet is loaded. The live plan is still calculated from the synthetic network.")

    meta = {
        "mode": mode,
        "status_title": status_title,
        "status_detail": status_detail,
        "warnings": warnings,
        "decision_year": int(decision_year),
        "length_note": length_note,
        "score_note": score_note,
        "files": {name: ("" if path is None else str(path)) for name, path in found.items()},
        "break_history": breaks is not None,
        "demonstrator": mode == "artifacts" and bool(manifest and "kitchener" in json.dumps(manifest).lower()),
        "panel_years": sorted(int(year) for year in panel["year"].dropna().unique()) if panel is not None and "year" in panel.columns else [],
        "manifest": manifest,
    }
    return {
        "pipes": pipes,
        "breaks": breaks,
        "panel": panel,
        "predictions": predictions,
        "metrics": metrics,
        "worklists": worklists,
        "meta": meta,
    }
