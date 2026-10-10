"""Independently check deliverables against unchanged raw GeoJSON.
Run from the delivered package: python validate_dataset.py
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", type=Path, default=Path(__file__).resolve().parent)
    args = ap.parse_args()
    base = args.package
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((base / "qa/data_quality_summary.json").read_text(encoding="utf-8"))
    p = json.loads((base / "raw/water_mains.geojson").read_text(encoding="utf-8-sig"))
    b = json.loads((base / "raw/water_main_break.geojson").read_text(encoding="utf-8-sig"))
    pipes = {int(f["properties"]["WATMAINID"]): f["properties"] for f in p["features"]}
    dates = {sid: parsedate_to_datetime(r["INSTALLATION_DATE"]).astimezone(timezone.utc) for sid, r in pipes.items()}
    accepted = defaultdict(list)
    ambiguous = set()
    clean_ids, rejected_ids = set(), set()
    for f in b["features"]:
        r = f["properties"]
        incident_id = int(r["WATBREAKINCIDENTID"])
        sid = r["ASSETID"]
        if r["BREAK_TYPE"] != "MAIN" or r["STATUS"] != "REPAIR COMPLETED" or sid not in pipes:
            rejected_ids.add(incident_id)
            continue
        date = parsedate_to_datetime(r["INCIDENT_DATE"]).astimezone(timezone.utc)
        if date < dates[sid]:
            ambiguous.add(sid)
            rejected_ids.add(incident_id)
            continue
        clean_ids.add(incident_id)
        accepted[sid].append(date)
    for events in accepted.values():
        events.sort()

    panel = pd.read_parquet(base / "data/pipe_year.parquet")
    features = pd.read_parquet(base / "data/features.parquet")
    outcomes = pd.read_parquet(base / "data/outcomes.parquet")
    clean_breaks = pd.read_parquet(base / "data/breaks_clean.parquet")
    assert set(clean_breaks.incident_id) == clean_ids
    assert len(clean_ids) + len(rejected_ids) == len(b["features"])
    assert set(panel.segment_id) <= pipes.keys()
    assert len(panel) == summary["pipe_year_rows"]
    assert not panel.duplicated(["segment_id", "year"]).any()
    assert panel.year.max() == manifest["policy"]["end_year"]
    assert panel.installation_year.lt(panel.year).all()
    pd.testing.assert_frame_equal(features[["segment_id", "score_date"]], outcomes[["segment_id", "score_date"]])
    forbidden = {"target_next_year_break", "target_break_count", "CONDITION_SCORE", "condition_score", "BREAK_APPARENT_CAUSE", "REPAIR_TYPE", "ambiguous_asset_history", "eligible_strict_history"}
    assert not forbidden.intersection(features.columns)
    assert set(manifest["model_feature_allowlist"]) <= set(features.columns)

    # Recompute target event keys from raw records, independently of pipeline tables.
    expected_counts = defaultdict(int)
    for sid, events in accepted.items():
        for event in events:
            if manifest["policy"]["start_year"] <= event.year <= manifest["policy"]["end_year"] and dates[sid].year < event.year:
                expected_counts[(sid, event.year)] += 1
    measured = {(int(r.segment_id), int(r.year)): int(r.target_break_count)
                for r in panel.loc[panel.target_break_count.gt(0), ["segment_id", "year", "target_break_count"]].itertuples(index=False)}
    assert dict(expected_counts) == measured
    assert int(panel.target_next_year_break.sum()) == len(expected_counts)
    assert int(panel.target_break_count.sum()) == sum(expected_counts.values())

    # Audit random rows, positive outcomes, and earliest exposure for every previously
    # ambiguous asset. Dates are parsed independently with the standard library.
    samples = pd.concat([
        panel.sample(n=min(500, len(panel)), random_state=42),
        panel.loc[panel.target_next_year_break.eq(1)].sample(n=min(150, int(panel.target_next_year_break.sum())), random_state=43),
        panel.loc[panel.segment_id.isin(ambiguous)].sort_values("year").groupby("segment_id").head(1),
    ]).drop_duplicates(["segment_id", "year"])
    for r in samples.itertuples(index=False):
        start = datetime(int(r.year), 1, 1, tzinfo=timezone.utc)
        end = datetime(int(r.year) + 1, 1, 1, tzinfo=timezone.utc)
        historical = [d for d in accepted.get(int(r.segment_id), []) if d < start]
        future = [d for d in accepted.get(int(r.segment_id), []) if start <= d < end]
        assert int(r.prior_break_count) == len(historical)
        assert int(r.target_break_count) == len(future)
        assert bool(r.target_next_year_break) == bool(future)
        if historical:
            elapsed = (start - max(historical)).total_seconds() / (365.25 * 86400)
            assert abs(float(r.years_since_last_break) - elapsed) < 1e-10
        else:
            assert pd.isna(r.years_since_last_break)
        assert bool(r.eligible_strict_history) == (int(r.segment_id) not in ambiguous)

    for stem, digest in manifest["raw_sha256"].items():
        assert hashlib.sha256((base / f"raw/{stem}.geojson").read_bytes()).hexdigest() == digest
    # Whole calendar exposure count is independently derived from raw install years.
    expected_rows = sum(max(0, manifest["policy"]["end_year"] - max(d.year + 1, manifest["policy"]["start_year"]) + 1) for d in dates.values())
    assert expected_rows == len(panel)
    mapping = json.loads((base / "data/pipes.geojson").read_text(encoding="utf-8"))
    assert len(mapping["features"]) == len(pipes)
    assert set(int(f["properties"]["segment_id"]) for f in mapping["features"]) == set(pipes)
    result = {
        "passed": True,
        "pipe_year_rows": len(panel),
        "all_target_counts_recomputed_from_raw": True,
        "sample_feature_histories_recomputed": len(samples),
        "raw_hashes_match": True,
        "feature_outcome_alignment": True,
        "whole_year_exposure_row_count_verified": True,
        "map_id_coverage_verified": True,
        "notes": "Integrity checks do not certify source completeness or resolve current-inventory survivor bias.",
    }
    (base / "qa/independent_validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
