# Data dictionary

| Field | Meaning |
|---|---|
| `segment_id` | WATMAINID, integer. Identifies current pipe. Identifier, not predictor. |
| `source_objectid` | Export/GIS feature identifier; not stable asset ID or predictor. |
| `year` | Calendar target year; score_date is Jan 1 UTC. |
| `score_date` | UTC cutoff. All history-derived features use strictly earlier incidents. |
| `target_end_date` | Exclusive Jan 1 of next year. Not predictor. |
| `installation_date` | Current inventory installation timestamp; historical precision may be approximate. |
| `installation_year` | Year from current installation date; no pipe-year in installation year. |
| `age_years` | Target year minus installation year (calendar-year age). |
| `material` | Original code; XXX/empty/null standardized to UNKNOWN. |
| `pipe_size_mm` | Positive PIPE_SIZE, interpreted in millimetres; otherwise null. |
| `length_m` | Geometry length after EPSG:4326 to EPSG:26917 projection, metres. |
| `prior_break_count` | Completed, linked, post-installation main incidents strictly before score_date; log-limited. |
| `last_prior_break_date` | Latest eligible prior incident timestamp; audit column, null if none. |
| `years_since_last_break` | Elapsed days / 365.25 since latest eligible prior break; null if no history. |
| `material_unknown` | True for standardized unknown material. |
| `pipe_size_missing` | True for nonpositive/missing PIPE_SIZE. |
| `installation_date_jan1` | Precision warning only: date is Jan 1. Not default model feature. |
| `target_next_year_break` | 0/1 for at least one eligible recorded incident in target window. Label. |
| `target_break_count` | Number of eligible recorded incidents in target window. Label, never predictor. |
| `outcome_coverage` | elapsed_year_completeness_assumed; not independently certified. Not predictor. |
| `ambiguous_asset_history` | Current ID has a matched completed incident before current installation. QA only. |
| `eligible_strict_history` | Complement of ambiguous_asset_history for sensitivity analysis; QA only. |
| `eligible_inventory` | Active current pipe, valid geometry, and known installation no later than snapshot; snapshot qualification, not historically verified status. |
| `geometry_valid` | Valid nonempty LineString or MultiLineString with positive metric length. |
| `current_status` | Current inventory status only; not historical predictor. |
| `incident_id` | Original WATBREAKINCIDENTID for retained incidents. |
| `incident_date` | Recorded GMT timestamp parsed as UTC. |
| `incident_year` | UTC calendar year of retained incident. |
