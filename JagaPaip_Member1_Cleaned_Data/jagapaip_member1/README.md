# JagaPaip Member 1 handoff

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
