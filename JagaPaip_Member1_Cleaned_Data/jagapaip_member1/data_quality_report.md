# JagaPaip — Member 1 data-quality report

Prepared from the two supplied Kitchener GeoJSON exports; snapshot recorded as 2026-10-10. This is a method demonstrator, not Malaysian validation. No model has been trained.

## Reconciliation

| Item | Count |
|---|---:|
| Raw pipes / unique WATMAINID | 16,214 / 16,214 |
| Raw break records | 3,022 |
| Non-main records excluded | 77 |
| Non-completed main records excluded | 18 |
| Invalid/future incident dates excluded | 0 |
| Completed main records with no matching pipe | 508 |
| Breaks on ineligible pipes | 0 |
| Matched breaks before current installation | 325 |
| Retained linked current-pipe incidents, all dates | 2,094 |

Every raw incident belongs to exactly one exclusion file or the retained incidents table. Raw records are copied byte-for-byte and hashed. IDs are unique in this specific export; no duplicate consolidation was necessary. Ten successful ID/date joins are in `qa/ten_join_examples.csv`; these are sample record checks, not independent physical confirmation of each pipe.

## Pipe-year table

- 340,035 rows across 1997–2025, covering 16,102 distinct pipes.
- 1,887 positive pipe-years (0.555%) and 2,020 recorded incidents in the labelled exposure windows. A pipe-year can have multiple incidents: do not confuse these metrics.
- 74 otherwise-clean incidents lie outside annual target exposure; the reasons are listed in `qa/clean_events_outside_panel_targets.csv`. Earlier incidents can still inform history. 2026 remains in clean incident data but never in full-year targets or earlier history.
- Eligible pipes must have been installed in an earlier calendar year. Installation-year targets are conservatively excluded because many installation dates appear year-precision only. History after installation can inform later years.
- Prior-break count and most recent prior break use only events strictly before score_date. No previous break is represented by count=0 and a missing years_since_last_break, not a fabricated elapsed time.
- `features.parquet` is physically separated from `outcomes.parquet`. `pipe_year.parquet` combines them for convenient modelling; select predictors using the manifest allowlist.

## Geometry and missingness

The exports use EPSG:4326 and omit Shape__Length. Lengths were calculated from complete LineString/MultiLineString geometry after projection to EPSG:26917. Current eligible network length is 938.550 km. An independent geodesic check differs by at most 0.03846%; projected lengths are finite and positive.

PIPE_SIZE is interpreted as mm, consistent with MAP_LABEL entries (e.g. 450mm). 2 nonpositive/missing sizes remain null. 1 unknown materials are standardized to UNKNOWN. No population-wide learned imputation or encoding has been fitted; Member 2 should fit any such transformations inside training folds.

Dates are parsed from explicit GMT text into UTC, avoiding a silent conversion to Malaysian time. 5,123 installation dates are January 1; this is a precision flag, not proof that all are estimates.

## Limitations and sensitivity

1. The inventory contains today's ACTIVE pipes. Removed/replaced assets are absent, and current attributes are not a historical asset register. This creates survivor bias that these files cannot eliminate.
2. 508 otherwise-accepted incidents are unmatched. They are not assigned to a nearby pipe or street. Report performance conditional on the linked, eligible current inventory, not all historical network failures. The denominator in evaluation must use outcomes for the same eligible inventory.
3. 325 incidents precede the current installation date, affecting 184 pipe IDs. They may describe predecessor pipes or errors. They do not count toward the current pipe's history or target. The `eligible_strict_history` flag supports a second evaluation that removes all affected IDs. This audit flag is not in the predictor allowlist.
4. Historical reporting completeness is not certified. Only a few accepted events occur before 1997; the panel begins in 1997 provisionally. The 1997–2025 annual target labels assume the supplied log is complete for eligible pipes. Review annual counts and consider early years as history/burn-in, with later years for evaluation. Zero means no eligible recorded incident, not guaranteed absence of a physical failure.
5. 2026 is incomplete and excluded as an annual target. 2025 is elapsed, but an elapsed year alone is not proof of complete reporting. Future additions to the city log may change counts.
6. CONDITION_SCORE, current rehabilitation indicators, incident cause/repair fields, and incident ASSET_* attributes are deliberately excluded from predictor outputs. Snapshot and work-order recording-time limitations remain; this is not a claim of fully leakage-free reconstruction.
7. The data validates neither avoided failures nor financial savings, and provides no evidence of Malaysian performance.

## Checks performed

Raw-file hashes; identifier uniqueness; exact incident reconciliation; many-to-one linkage; valid metric lengths with independent geodesic comparison; unique pipe-year keys; full-year exposure; historical feature cutoffs; consistency of binary and count targets; incident-to-panel target reconciliation; no outcomes in the feature-only file; round-trip Parquet schema/value checks. Independent validation recomputed all target counts from the raw files and checked 833 sampled feature histories; see qa/independent_validation.json. These checks do not certify source completeness.
