"""Reproducible JagaPaip Member 1 preparation. No model training.

Run: python build_dataset.py --output .
Defaults read raw/water_mains.geojson and raw/water_main_break.geojson
relative to this script. See README.md for assumptions and field allowlist.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow
import pyproj
import shapely
from pyproj import Geod, Transformer
from shapely.geometry import shape
from shapely.ops import transform


SOURCES = {
    "water_mains": "https://open-kitchenergis.opendata.arcgis.com/datasets/KitchenerGIS::water-mains/about",
    "water_main_break": "https://open-kitchenergis.opendata.arcgis.com/datasets/KitchenerGIS::water-main-breaks/about",
}
SAFE_FEATURES = ["age_years", "material", "pipe_size_mm", "length_m", "prior_break_count",
                 "years_since_last_break", "material_unknown", "pipe_size_missing"]
DATE_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def parse_date(series):
    return pd.to_datetime(series, format=DATE_FORMAT, errors="coerce", utc=True)


def main():
    base = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--mains", type=Path, default=base / "raw/water_mains.geojson")
    ap.add_argument("--breaks", type=Path, default=base / "raw/water_main_break.geojson")
    ap.add_argument("--output", type=Path, default=base)
    ap.add_argument("--snapshot-date", default="2026-10-10")
    ap.add_argument("--start-year", type=int, default=1997)
    ap.add_argument("--end-year", type=int, default=2025)
    args = ap.parse_args()
    out = args.output.resolve()
    snapshot = pd.Timestamp(args.snapshot_date, tz="UTC")
    assert args.start_year <= args.end_year < snapshot.year, "Only elapsed calendar years are annual targets"
    for folder in ("raw", "data", "exceptions", "qa"):
        (out / folder).mkdir(parents=True, exist_ok=True)

    source_hashes = {"water_mains": sha(args.mains), "water_main_break": sha(args.breaks)}
    for src, name in ((args.mains, "water_mains.geojson"), (args.breaks, "water_main_break.geojson")):
        dest = out / "raw" / name
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        assert sha(src) == sha(dest)

    mj = json.loads(args.mains.read_text(encoding="utf-8-sig"))
    bj = json.loads(args.breaks.read_text(encoding="utf-8-sig"))
    assert mj["crs"]["properties"]["name"] == "EPSG:4326"
    assert bj["crs"]["properties"]["name"] == "EPSG:4326"
    raw_p = pd.DataFrame([f["properties"] for f in mj["features"]])
    raw_b = pd.DataFrame([f["properties"] for f in bj["features"]])

    # Stop rather than choose an arbitrary geometry or duplicate an incident.
    duplicates_p = raw_p[raw_p.WATMAINID.duplicated(keep=False)]
    duplicates_b = raw_b[raw_b.WATBREAKINCIDENTID.duplicated(keep=False)]
    duplicates_p.to_csv(out / "exceptions/duplicate_pipe_ids.csv", index=False)
    duplicates_b.to_csv(out / "exceptions/duplicate_incident_ids.csv", index=False)
    assert raw_p.WATMAINID.notna().all() and duplicates_p.empty, "Resolve ambiguous pipe IDs explicitly"
    assert raw_b.WATBREAKINCIDENTID.notna().all() and duplicates_b.empty, "Resolve duplicate incidents explicitly"

    project = Transformer.from_crs(4326, 26917, always_xy=True).transform
    geod = Geod(ellps="GRS80")
    lengths, length_errors, geometry_ok = [], [], []
    for f in mj["features"]:
        try:
            geom = shape(f["geometry"])
            valid = geom.geom_type in {"LineString", "MultiLineString"} and geom.is_valid and not geom.is_empty
            assert valid
            length = transform(project, geom).length
            geod_length = geod.geometry_length(geom)
            assert np.isfinite(length) and length > 0 and geod_length > 0
            lengths.append(length)
            length_errors.append(abs(length / geod_length - 1))
            geometry_ok.append(True)
        except Exception:
            lengths.append(np.nan)
            length_errors.append(np.nan)
            geometry_ok.append(False)

    p = pd.DataFrame({
        "segment_id": raw_p.WATMAINID.astype("int64"),
        "source_objectid": raw_p.OBJECTID.astype("int64"),
        "installation_date": parse_date(raw_p.INSTALLATION_DATE),
        "material": raw_p.MATERIAL.fillna("UNKNOWN").str.strip().str.upper().replace({"XXX": "UNKNOWN", "": "UNKNOWN"}),
        "pipe_size_mm": pd.to_numeric(raw_p.PIPE_SIZE, errors="coerce").where(lambda x: x > 0),
        "length_m": lengths,
        "geometry_valid": geometry_ok,
        "current_status": raw_p.STATUS,
    })
    p["installation_year"] = p.installation_date.dt.year.astype("Int64")
    p["installation_date_jan1"] = p.installation_date.dt.month.eq(1) & p.installation_date.dt.day.eq(1)
    p["material_unknown"] = p.material.eq("UNKNOWN")
    p["pipe_size_missing"] = p.pipe_size_mm.isna()
    p["eligible_inventory"] = p.geometry_valid & p.installation_date.notna() & p.installation_date.le(snapshot) & p.current_status.eq("ACTIVE")
    p.loc[~p.eligible_inventory].to_csv(out / "exceptions/ineligible_pipes.csv", index=False)

    # Mutually exclusive event exclusions, in this documented order.
    ex = {}
    def exclude(frame, mask, reason):
        rejected = frame.loc[mask].copy()
        rejected["exclusion_reason"] = reason
        rejected.to_csv(out / f"exceptions/{reason}.csv", index=False)
        ex[reason] = len(rejected)
        return frame.loc[~mask].copy()

    b = exclude(raw_b, ~raw_b.BREAK_TYPE.eq("MAIN"), "non_main_breaks")
    b = exclude(b, ~b.STATUS.eq("REPAIR COMPLETED"), "non_completed_main_breaks")
    b["incident_date"] = parse_date(b.INCIDENT_DATE)
    b = exclude(b, b.incident_date.isna() | b.incident_date.ge(snapshot + pd.Timedelta(days=1)), "invalid_or_future_incident_dates")
    b["segment_id"] = pd.to_numeric(b.ASSETID, errors="coerce").astype("Int64")
    b = b.merge(p[["segment_id", "installation_date", "eligible_inventory"]], on="segment_id", how="left", validate="many_to_one", indicator=True)
    b = exclude(b, b._merge.ne("both"), "unmatched_main_breaks")
    matched_completed_count = len(b)
    ambiguous_ids = set(b.loc[b.incident_date.lt(b.installation_date), "segment_id"].astype(int))
    b = exclude(b, b.installation_date.isna() | b.eligible_inventory.ne(True), "breaks_on_ineligible_pipes")
    b = exclude(b, b.incident_date.lt(b.installation_date), "pre_installation_breaks")
    clean_b = b[["WATBREAKINCIDENTID", "segment_id", "incident_date"]].rename(columns={"WATBREAKINCIDENTID": "incident_id"})
    clean_b = clean_b.astype({"incident_id": "int64", "segment_id": "int64"}).sort_values(["segment_id", "incident_date", "incident_id"]).reset_index(drop=True)
    clean_b["incident_year"] = clean_b.incident_date.dt.year.astype("int16")
    p["ambiguous_asset_history"] = p.segment_id.isin(ambiguous_ids)
    p = p.sort_values("segment_id").reset_index(drop=True)

    # One full calendar year of exposure. Installation year is deliberately excluded
    # even when its date is Jan 1: many dates have only year-level precision.
    panels = []
    for year in range(args.start_year, args.end_year + 1):
        score = pd.Timestamp(year=year, month=1, day=1, tz="UTC")
        end = pd.Timestamp(year=year + 1, month=1, day=1, tz="UTC")
        q = p.loc[p.eligible_inventory & p.installation_year.lt(year)].copy()
        q["year"] = np.int16(year)
        q["score_date"] = score
        q["target_end_date"] = end
        q["age_years"] = (year - q.installation_year).astype("int16")
        history = clean_b.loc[clean_b.incident_date.lt(score)]
        counts = history.groupby("segment_id").size()
        last = history.groupby("segment_id").incident_date.max()
        q["prior_break_count"] = q.segment_id.map(counts).fillna(0).astype("int16")
        q["last_prior_break_date"] = q.segment_id.map(last)
        q["years_since_last_break"] = (score - q.last_prior_break_date).dt.total_seconds() / (365.25 * 86400)
        target = clean_b.loc[clean_b.incident_date.ge(score) & clean_b.incident_date.lt(end)].groupby("segment_id").size()
        q["target_break_count"] = q.segment_id.map(target).fillna(0).astype("int16")
        q["target_next_year_break"] = q.target_break_count.gt(0).astype("int8")
        q["eligible_strict_history"] = ~q.ambiguous_asset_history
        q["outcome_coverage"] = "elapsed_year_completeness_assumed"
        panels.append(q)
    panel = pd.concat(panels, ignore_index=True).sort_values(["year", "segment_id"]).reset_index(drop=True)
    outcomes_cols = ["segment_id", "year", "score_date", "target_end_date", "target_next_year_break", "target_break_count", "outcome_coverage"]
    feature_cols = ["segment_id", "year", "score_date", "installation_year", "age_years", "material", "pipe_size_mm", "length_m", "prior_break_count", "years_since_last_break", "material_unknown", "pipe_size_missing", "installation_date_jan1"]
    qa_cols = ["segment_id", "year", "last_prior_break_date", "ambiguous_asset_history", "eligible_strict_history"]
    panel.to_parquet(out / "data/pipe_year.parquet", index=False, compression="zstd")
    panel[feature_cols].to_parquet(out / "data/features.parquet", index=False, compression="zstd")
    panel[outcomes_cols].to_parquet(out / "data/outcomes.parquet", index=False, compression="zstd")
    panel[qa_cols].to_parquet(out / "qa/pipe_year_audit.parquet", index=False, compression="zstd")
    p.to_parquet(out / "data/pipes_clean.parquet", index=False, compression="zstd")
    clean_b.to_parquet(out / "data/breaks_clean.parquet", index=False, compression="zstd")

    byid = p.set_index("segment_id")
    map_features = []
    for f in mj["features"]:
        sid = int(f["properties"]["WATMAINID"])
        r = byid.loc[sid]
        if not r.eligible_inventory:
            continue
        map_features.append({"type": "Feature", "id": sid, "geometry": f["geometry"], "properties": {
            "segment_id": sid, "material": r.material, "installation_year": int(r.installation_year),
            "pipe_size_mm": None if pd.isna(r.pipe_size_mm) else float(r.pipe_size_mm),
            "length_m": float(r.length_m), "material_unknown": bool(r.material_unknown),
            "ambiguous_asset_history": bool(r.ambiguous_asset_history)}})
    write_json(out / "data/pipes.geojson", {"type": "FeatureCollection", "features": map_features})

    raw_main_completed = raw_b.loc[raw_b.BREAK_TYPE.eq("MAIN") & raw_b.STATUS.eq("REPAIR COMPLETED")].copy()
    raw_main_completed["year"] = parse_date(raw_main_completed.INCIDENT_DATE).dt.year
    annual = pd.DataFrame({"completed_main_raw": raw_main_completed.groupby("year").size(),
                           "clean_linked_incidents": clean_b.groupby("incident_year").size()}).fillna(0).astype(int)
    annual.index.name = "year"
    summaries = panel.groupby("year").agg(pipe_year_rows=("segment_id", "size"), network_length_m=("length_m", "sum"), positive_pipe_years=("target_next_year_break", "sum"), target_incidents=("target_break_count", "sum"))
    summaries["positive_rate"] = summaries.positive_pipe_years / summaries.pipe_year_rows
    annual.join(summaries, how="outer").to_csv(out / "qa/annual_coverage.csv")
    # Clean events outside panel targets are not silently lost: they can still be history.
    target_keys = pd.MultiIndex.from_frame(panel[["segment_id", "year"]])
    event_keys = pd.MultiIndex.from_frame(clean_b[["segment_id", "incident_year"]].rename(columns={"incident_year": "year"}))
    outside = clean_b.loc[~event_keys.isin(target_keys)].copy()
    outside["reason"] = np.select([outside.incident_year.lt(args.start_year), outside.incident_year.gt(args.end_year)],
                                   ["before_panel_window_history_only", "after_panel_window_not_full_year_target"], default="installation_year_not_full_exposure")
    outside.to_csv(out / "qa/clean_events_outside_panel_targets.csv", index=False)
    examples = clean_b.merge(p, on="segment_id", validate="many_to_one").sort_values(["incident_date", "incident_id"])
    indices = np.linspace(0, len(examples) - 1, min(10, len(examples)), dtype=int)
    examples.iloc[indices][["incident_id", "segment_id", "installation_date", "incident_date", "material", "pipe_size_mm", "length_m", "ambiguous_asset_history"]].to_csv(out / "qa/ten_join_examples.csv", index=False)

    # Meaningful integrity checks: accounting, exposure, feature timing and persistence.
    assert len(raw_b) == sum(ex.values()) + len(clean_b)
    assert not panel.duplicated(["segment_id", "score_date"]).any()
    assert panel.installation_year.lt(panel.year).all()
    assert panel.last_prior_break_date.dropna().lt(panel.loc[panel.last_prior_break_date.notna(), "score_date"]).all()
    assert panel.years_since_last_break.dropna().ge(0).all()
    assert panel.loc[panel.prior_break_count.eq(0), "years_since_last_break"].isna().all()
    assert panel.target_next_year_break.eq(panel.target_break_count.gt(0).astype(int)).all()
    assert int(panel.target_break_count.sum()) + len(outside) == len(clean_b)
    assert (panel.length_m > 0).all()
    assert max(e for e in length_errors if np.isfinite(e)) < 0.005
    assert not any(c.startswith("target_") for c in feature_cols)
    for filename, frame in [("pipe_year", panel), ("features", panel[feature_cols]), ("outcomes", panel[outcomes_cols]), ("pipes_clean", p), ("breaks_clean", clean_b)]:
        restored = pd.read_parquet(out / f"data/{filename}.parquet")
        pd.testing.assert_frame_equal(restored, frame)
    assert source_hashes == {"water_mains": sha(args.mains), "water_main_break": sha(args.breaks)}

    stats = {
        "raw_pipe_features": len(raw_p), "unique_pipe_ids": int(raw_p.WATMAINID.nunique()),
        "raw_breaks": len(raw_b), "completed_main_breaks": len(raw_main_completed),
        "matched_completed_main_breaks": matched_completed_count, "exclusions": ex,
        "clean_linked_breaks_all_dates": len(clean_b), "ambiguous_history_pipes": len(ambiguous_ids),
        "eligible_inventory_pipes": int(p.eligible_inventory.sum()), "network_km": float(p.loc[p.eligible_inventory, "length_m"].sum() / 1000),
        "missing_pipe_size": int(p.pipe_size_missing.sum()), "unknown_material": int(p.material_unknown.sum()),
        "jan1_installation_dates": int(p.installation_date_jan1.sum()),
        "panel_start_year": args.start_year, "panel_end_year": args.end_year,
        "pipe_year_rows": len(panel), "unique_panel_pipes": int(panel.segment_id.nunique()),
        "positive_pipe_years": int(panel.target_next_year_break.sum()), "positive_rate": float(panel.target_next_year_break.mean()),
        "target_incidents": int(panel.target_break_count.sum()), "clean_events_outside_panel_targets": len(outside),
        "strict_history_rows": int(panel.eligible_strict_history.sum()),
        "strict_history_positive_pipe_years": int(panel.loc[panel.eligible_strict_history, "target_next_year_break"].sum()),
        "max_projected_vs_geodesic_relative_difference": float(np.nanmax(length_errors)),
        "checks_passed": True,
    }
    write_json(out / "qa/data_quality_summary.json", stats)
    manifest = {"schema_version": "1.0.0", "snapshot_date": args.snapshot_date, "source_urls": SOURCES,
                "raw_sha256": source_hashes, "date_timezone": "UTC", "input_and_map_crs": "EPSG:4326", "length_crs": "EPSG:26917",
                "model_feature_allowlist": SAFE_FEATURES,
                "policy": {"start_year": args.start_year, "end_year": args.end_year, "break_filter": "BREAK_TYPE=MAIN and STATUS=REPAIR COMPLETED", "join": "ASSETID=WATMAINID; many incidents to one unique pipe", "exposure": "installation_year < target year; whole-year exposure", "target": "at least one eligible recorded incident in [score_date,target_end_date)", "historical_completeness": "assumed for 1997-2025, not certified; inspect annual_coverage.csv", "strict_sensitivity": "exclude ambiguous_asset_history pipes using qa/pipe_year_audit.parquet"},
                "versions": {"pandas": pd.__version__, "numpy": np.__version__, "pyarrow": pyarrow.__version__, "pyproj": pyproj.__version__, "shapely": shapely.__version__}}
    write_json(out / "manifest.json", manifest)

    report = f"""# JagaPaip — Member 1 data-quality report

Prepared from the two supplied Kitchener GeoJSON exports; snapshot recorded as {args.snapshot_date}. This is a method demonstrator, not Malaysian validation. No model has been trained.

## Reconciliation

| Item | Count |
|---|---:|
| Raw pipes / unique WATMAINID | {len(raw_p):,} / {raw_p.WATMAINID.nunique():,} |
| Raw break records | {len(raw_b):,} |
| Non-main records excluded | {ex['non_main_breaks']:,} |
| Non-completed main records excluded | {ex['non_completed_main_breaks']:,} |
| Invalid/future incident dates excluded | {ex['invalid_or_future_incident_dates']:,} |
| Completed main records with no matching pipe | {ex['unmatched_main_breaks']:,} |
| Breaks on ineligible pipes | {ex['breaks_on_ineligible_pipes']:,} |
| Matched breaks before current installation | {ex['pre_installation_breaks']:,} |
| Retained linked current-pipe incidents, all dates | {len(clean_b):,} |

Every raw incident belongs to exactly one exclusion file or the retained incidents table. Raw records are copied byte-for-byte and hashed. IDs are unique in this specific export; no duplicate consolidation was necessary. Ten successful ID/date joins are in `qa/ten_join_examples.csv`; these are sample record checks, not independent physical confirmation of each pipe.

## Pipe-year table

- {len(panel):,} rows across {args.start_year}–{args.end_year}, covering {panel.segment_id.nunique():,} distinct pipes.
- {int(panel.target_next_year_break.sum()):,} positive pipe-years ({panel.target_next_year_break.mean():.3%}) and {int(panel.target_break_count.sum()):,} recorded incidents in the labelled exposure windows. A pipe-year can have multiple incidents: do not confuse these metrics.
- {len(outside):,} otherwise-clean incidents lie outside annual target exposure; the reasons are listed in `qa/clean_events_outside_panel_targets.csv`. Earlier incidents can still inform history. 2026 remains in clean incident data but never in full-year targets or earlier history.
- Eligible pipes must have been installed in an earlier calendar year. Installation-year targets are conservatively excluded because many installation dates appear year-precision only. History after installation can inform later years.
- Prior-break count and most recent prior break use only events strictly before score_date. No previous break is represented by count=0 and a missing years_since_last_break, not a fabricated elapsed time.
- `features.parquet` is physically separated from `outcomes.parquet`. `pipe_year.parquet` combines them for convenient modelling; select predictors using the manifest allowlist.

## Geometry and missingness

The exports use EPSG:4326 and omit Shape__Length. Lengths were calculated from complete LineString/MultiLineString geometry after projection to EPSG:26917. Current eligible network length is {stats['network_km']:.3f} km. An independent geodesic check differs by at most {stats['max_projected_vs_geodesic_relative_difference']:.5%}; projected lengths are finite and positive.

PIPE_SIZE is interpreted as mm, consistent with MAP_LABEL entries (e.g. 450mm). {int(p.pipe_size_missing.sum()):,} nonpositive/missing sizes remain null. {int(p.material_unknown.sum()):,} unknown materials are standardized to UNKNOWN. No population-wide learned imputation or encoding has been fitted; Member 2 should fit any such transformations inside training folds.

Dates are parsed from explicit GMT text into UTC, avoiding a silent conversion to Malaysian time. {int(p.installation_date_jan1.sum()):,} installation dates are January 1; this is a precision flag, not proof that all are estimates.

## Limitations and sensitivity

1. The inventory contains today's ACTIVE pipes. Removed/replaced assets are absent, and current attributes are not a historical asset register. This creates survivor bias that these files cannot eliminate.
2. {ex['unmatched_main_breaks']:,} otherwise-accepted incidents are unmatched. They are not assigned to a nearby pipe or street. Report performance conditional on the linked, eligible current inventory, not all historical network failures. The denominator in evaluation must use outcomes for the same eligible inventory.
3. {ex['pre_installation_breaks']:,} incidents precede the current installation date, affecting {len(ambiguous_ids):,} pipe IDs. They may describe predecessor pipes or errors. They do not count toward the current pipe's history or target. The `eligible_strict_history` flag supports a second evaluation that removes all affected IDs. This audit flag is not in the predictor allowlist.
4. Historical reporting completeness is not certified. Only a few accepted events occur before 1997; the panel begins in 1997 provisionally. The 1997–2025 annual target labels assume the supplied log is complete for eligible pipes. Review annual counts and consider early years as history/burn-in, with later years for evaluation. Zero means no eligible recorded incident, not guaranteed absence of a physical failure.
5. 2026 is incomplete and excluded as an annual target. 2025 is elapsed, but an elapsed year alone is not proof of complete reporting. Future additions to the city log may change counts.
6. CONDITION_SCORE, current rehabilitation indicators, incident cause/repair fields, and incident ASSET_* attributes are deliberately excluded from predictor outputs. Snapshot and work-order recording-time limitations remain; this is not a claim of fully leakage-free reconstruction.
7. The data validates neither avoided failures nor financial savings, and provides no evidence of Malaysian performance.

## Checks performed

Raw-file hashes; identifier uniqueness; exact incident reconciliation; many-to-one linkage; valid metric lengths with independent geodesic comparison; unique pipe-year keys; full-year exposure; historical feature cutoffs; consistency of binary and count targets; incident-to-panel target reconciliation; no outcomes in the feature-only file; round-trip Parquet schema/value checks. Run validate_dataset.py for independent raw-record target and feature-history checks; its results are saved in qa/independent_validation.json.
"""
    (out / "data_quality_report.md").write_text(report, encoding="utf-8")
    readme = """# JagaPaip Member 1 handoff

Start with data/pipe_year.parquet and data_quality_report.md. No model or evaluation score is included.

## Files

- data/pipe_year.parquet — one eligible current-pipe × calendar-year row, including predictors, labels and audit fields.
- data/features.parquet — feature-only companion; no future outcomes.
- data/outcomes.parquet — annual labels. Join on segment_id + score_date.
- data/pipes_clean.parquet — typed current inventory and quality flags.
- data/breaks_clean.parquet — completed, linked, post-installation main incidents, including dates outside panel targets.
- data/pipes.geojson — geometry in longitude/latitude, keyed by segment_id, with length_m calculated in a projected metre CRS.
- qa/pipe_year_audit.parquet — historical cutoff and strict sensitivity flags.
- qa/annual_coverage.csv — counts and eligible kilometres per year.
- qa/ten_join_examples.csv — examples for human review.
- qa/clean_events_outside_panel_targets.csv — clean incidents without a full-year target row, with reasons.
- exceptions/ — mutually exclusive rejected event groups, plus pipe and duplicate checks. Empty files retain headers.
- raw/ — unchanged source downloads.
- manifest.json — source URLs, SHA256 hashes, policy and software versions.

## Member 2

Target: target_next_year_break. Group key: segment_id. Temporal key: score_date.
Use only the manifest's model_feature_allowlist as default predictors. Do not train on IDs, source_objectid, target_break_count, target_end_date, outcome_coverage, current_status or QA flags. Exclude target_next_year_break from X. Keep chronological splits and fit encoders/imputers on training folds only. Never randomly split pipe-year rows. Evaluate the ambiguous-history exclusion sensitivity. Dates/lengths/labels are prepared, but no model scaling or learned preprocessing is performed.

## Member 3

Budget using length_m. The eligible annual inventory is the set of segment_id values for that score_date, not every current pipe. Use the same eligible rows in every baseline. Only Member 2's out-of-time scores should drive Proof Mode; outcomes must not enter selection.

## Member 4

Join scored segment_id values to data/pipes.geojson. Geometry is EPSG:4326. Display years, capacity used and source label. Read outcomes only for reveal/evaluation. Display Kitchener open-data demonstrator, Malaysian validation pending.

## Rebuild

Install requirements.txt into a Python environment, then run:

    python build_dataset.py --output .

Defaults use the included raw files, snapshot date 2026-10-10, and panel years 1997–2025. For a new snapshot, set --snapshot-date explicitly and review the year/coverage policy. This script intentionally stops on duplicate asset or incident IDs rather than silently guessing a resolution. Run validate_dataset.py after rebuilding.
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    dictionary = {
        "segment_id": "WATMAINID, integer. Identifies current pipe. Identifier, not predictor.",
        "source_objectid": "Export/GIS feature identifier; not stable asset ID or predictor.",
        "year": "Calendar target year; score_date is Jan 1 UTC.",
        "score_date": "UTC cutoff. All history-derived features use strictly earlier incidents.",
        "target_end_date": "Exclusive Jan 1 of next year. Not predictor.",
        "installation_date": "Current inventory installation timestamp; historical precision may be approximate.",
        "installation_year": "Year from current installation date; no pipe-year in installation year.",
        "age_years": "Target year minus installation year (calendar-year age).",
        "material": "Original code; XXX/empty/null standardized to UNKNOWN.",
        "pipe_size_mm": "Positive PIPE_SIZE, interpreted in millimetres; otherwise null.",
        "length_m": "Geometry length after EPSG:4326 to EPSG:26917 projection, metres.",
        "prior_break_count": "Completed, linked, post-installation main incidents strictly before score_date; log-limited.",
        "last_prior_break_date": "Latest eligible prior incident timestamp; audit column, null if none.",
        "years_since_last_break": "Elapsed days / 365.25 since latest eligible prior break; null if no history.",
        "material_unknown": "True for standardized unknown material.",
        "pipe_size_missing": "True for nonpositive/missing PIPE_SIZE.",
        "installation_date_jan1": "Precision warning only: date is Jan 1. Not default model feature.",
        "target_next_year_break": "0/1 for at least one eligible recorded incident in target window. Label.",
        "target_break_count": "Number of eligible recorded incidents in target window. Label, never predictor.",
        "outcome_coverage": "elapsed_year_completeness_assumed; not independently certified. Not predictor.",
        "ambiguous_asset_history": "Current ID has a matched completed incident before current installation. QA only.",
        "eligible_strict_history": "Complement of ambiguous_asset_history for sensitivity analysis; QA only.",
        "eligible_inventory": "Active current pipe, valid geometry, and known installation no later than snapshot; snapshot qualification, not historically verified status.",
        "geometry_valid": "Valid nonempty LineString or MultiLineString with positive metric length.",
        "current_status": "Current inventory status only; not historical predictor.",
        "incident_id": "Original WATBREAKINCIDENTID for retained incidents.",
        "incident_date": "Recorded GMT timestamp parsed as UTC.",
        "incident_year": "UTC calendar year of retained incident.",
    }
    (out / "data_dictionary.md").write_text("# Data dictionary\n\n| Field | Meaning |\n|---|---|\n" + "\n".join(f"| `{k}` | {v} |" for k, v in dictionary.items()) + "\n", encoding="utf-8")
    versions = manifest["versions"]
    (out / "requirements.txt").write_text("\n".join(f"{k}=={v}" for k, v in versions.items()) + "\n", encoding="utf-8")
    script_dest = out / "build_dataset.py"
    if Path(__file__).resolve() != script_dest.resolve():
        shutil.copy2(__file__, script_dest)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
