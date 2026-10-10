# JagaPaip model card

**Owner:** Member 2 (ML & Evaluation). **Status:** draft, pre-H12 freeze.
**Contract versions:** reads Contract A 1.0, writes Contract B 1.0 and `metrics.json` 1.0.

> Every measured number comes from `artifacts/metrics.json`. Do not type result values into this card, the slides or the UI. If this card and `metrics.json` disagree, `metrics.json` wins.

## 1. Intended use

- **Use:** rank water-main segments by next-year break risk, so an asset manager can choose which kilometres to inspect or review for renewal under a fixed length budget. The test is a historical "hide, decide, reveal" comparison against simple planning rules.
- **Not for:** ordering excavation or replacement automatically, estimating money saved or breaks prevented, or making claims about Malaysian networks. Malaysian performance is untested until a utility retrospective pilot.

## 2. Prediction target

| Item | Definition |
|---|---|
| Unit | pipe segment x score year (one Contract A row) |
| Target | `target_next_year_break`: at least one recorded break during `[1 Jan Y, 1 Jan Y+1)` |
| Output | `model_score` (raw) and `risk_percentile` (within-year rank, 0 to 1, larger means riskier) |
| Not output | calibrated probabilities. Percentiles are rankings. |

## 3. Data

Input is Member 1's data package in `data/` (Kitchener open data, snapshot 2026-10-10). See `data/data_quality_report.md` and `data/data_dictionary.md` for sources, joins and exclusions.

- **Adapter.** Member 1's `data/data/pipe_year.parquet` uses its own field names. `src/modeling/adapters.py` maps it onto Contract A, and `--write-contract-a` saves the result as `artifacts/pipe_year.parquet` for Members 3 and 4. Mapping decisions:
  - fields are renamed (`year`→`score_year`, `installation_year`→`install_year`, `pipe_size_mm`→`diameter_mm`, `ambiguous_asset_history`→`is_ambiguous_history`), and `segment_id` becomes a string;
  - `data_quality_flags` is built from `material_unknown`, `pipe_size_missing` and `ambiguous_asset_history`. `installation_date_jan1` is left out: it marks year-only date precision on about 43% of rows, and flagging it would downgrade half the network to MEDIUM over ±1 year of age;
  - `source_snapshot_date` comes from `data/manifest.json`.
- **Burn-in.** Score years before 2000 are dropped (`--first-score-year`). The break log starts in 1997, so those years have almost no recorded history; Member 1's report recommends treating them as burn-in. Their breaks still count toward later years' history.
- **Predictors** stay within Member 1's allowlist: age, material, pipe size, length, prior breaks, years since last break, plus the install decade, which follows from age and score year.
- The input must pass `validate_pipe_year` in `src/modeling/contracts.py` before modeling runs.
- **Primary panel:** excludes rows with `is_ambiguous_history = true`.
- **Sensitivity:** reruns with ambiguous rows included, blanking negative ages. The result is reported under `metrics.json -> sensitivity`.

## 4. Evaluation protocol

1. **Walk-forward, expanding window.** Test year `Y` trains on every score year `< Y`. No random row split exists in result code, and a test enforces this.
2. **Complete years only.** Year `Y` counts only if `source_snapshot_date` is on or after 1 Jan `Y+1`. Later score years are dropped, and requesting one as a test year is an error. With the October 2026 Kitchener download, the last usable year is 2025. `metrics.json -> inputs` records `outcomes_complete_through` and the excluded years. Real data must carry a date snapshot.
3. **Point-in-time features.** Contract A guarantees history features use only events before 1 Jan `Y`. Fitted preprocessing (imputation, scaling, encodings, lookup rates) is fitted inside each training fold.
4. **Equal length budget.** Within a test year, every method ranks the same eligible segments. The budget is `budget x total length` of those segments, so every method gets exactly the same metres.
5. **Ordering:** `risk_percentile` descending, then `segment_id` ascending.
6. **Selection:** keep the longest prefix of that ordering whose cumulative `length_m` does not exceed the budget. Stop at the first overflow; do not skip ahead.
7. **Budgets:** 1%, 2%, 5% and 10% of network length. The primary budget is 5%.

Members 3 and 4 must reproduce the same ordering and selection. `metrics_consistency_errors` checks that the per-year counts in `metrics.json` match Contract B exactly.

## 5. Methods (baseline ladder)

| Method | Score | Fitted on training years? |
|---|---|---|
| `random` | seeded hash of (seed, year, segment_id) | no |
| `oldest` | `age_years`; unknown age ranks last | no |
| `prior_breaks` | `prior_break_count` | no |
| `lookup` | smoothed break rate: global -> prior-break bucket (0/1/2+) -> material -> install decade, with shrinkage `(events + k*parent)/(n + k)` and `k = 100` | yes |
| `logistic` | L2 logistic discrete-time hazard on age, log length, log diameter, log prior breaks, break recency, nearby prior breaks, material and decade | yes |

A boosted-tree challenger is optional. It is the first item cut if time is short.

## 6. Champion selection

Rule (also recorded in `metrics.json`): highest mean `capture_at_05` across test years among non-random methods. A tie to 4 decimal places goes to the simpler method, in the order `oldest < prior_breaks < lookup < logistic`.

- Contract B labels the winner's rows `champion`; `metrics.json -> champion_method` names it.
- **Freeze (H12):** select the measured champion. If a lookup or baseline wins, ship it and say so. After the freeze, fix only correctness bugs.

## 7. Confidence and out-of-distribution (OOD)

Confidence measures evidence support, not risk. It uses training years only and is the same for every method in a year.

| Label | Rule |
|---|---|
| `is_ood` | material unseen in training or `UNKNOWN`; missing age; or age more than 5 years outside the training range |
| `LOW` | `is_ood`, or fewer than 30 training pipe-years share the material x install decade |
| `MEDIUM` | fewer than 200 such pipe-years, or quality flags, missing diameter, or an ambiguous history |
| `HIGH` | otherwise |

Member 3's policy routes `LOW`/OOD rows to inspection, never to automatic renewal review.

## 8. Metrics glossary

| Metric | Meaning | Across years |
|---|---|---|
| `capture_at_XX` | share of the year's broken segments inside the XX% length budget | mean |
| `precision_at_XX` | share of selected segments with a recorded break | mean |
| `observed_non_events_at_XX` | selected segments without a recorded break | sum |
| `lift_vs_oldest_at_05` | `capture_at_05` divided by oldest-first's value | ratio of means |
| `years_beating_oldest_at_05` | test years where the method beat oldest-first | count |
| `capture_at_05_std/min/max` | variation across test years | |
| `pr_auc_mean` | average precision; a diagnostic, not the decision metric | mean |

Capture counts segments with at least one break, not individual break events. An observed non-event is not proof that inspecting the segment was useless.

**Uncertainty (`metrics.json -> uncertainty`).** This is a paired segment bootstrap: within each test year, segments are resampled with replacement (1,000 resamples) and every method is judged on the same resample.

| Field | Meaning |
|---|---|
| `capture.budget_X.<method>.ci_mean` | 95% interval for the across-year mean capture |
| `capture.budget_X.<method>.by_year` | 95% interval for each test year |
| `difference_vs_oldest.budget_X.<method>.ci_mean` | 95% interval for (method - oldest) capture |
| `share_of_resamples_above_zero` | how often the method beat oldest-first across resamples. This is a stability measure, not a p-value. |

The interval covers segment-sampling noise within the observed years. It does not cover year-to-year change, the random baseline's single draw, or differences between Kitchener and Malaysia.

## 9. Results

Read them from `artifacts/metrics.json`. The Contract B fixture in `contracts/fixtures/` is **synthetic** (`is_synthetic: true`): its numbers are schema examples and must never appear on slides.

| Method | Capture@5% | Precision@5% | Observed non-events | Lift vs oldest |
|---|---:|---:|---:|---:|
| random | `[metrics.json]` | `[metrics.json]` | `[metrics.json]` | `[metrics.json]` |
| oldest | `[metrics.json]` | `[metrics.json]` | `[metrics.json]` | 1.00x |
| prior_breaks | `[metrics.json]` | `[metrics.json]` | `[metrics.json]` | `[metrics.json]` |
| champion | `[metrics.json]` | `[metrics.json]` | `[metrics.json]` | `[metrics.json]` |

## 10. Robustness (status)

- [x] Ambiguous-history sensitivity (`metrics.json -> sensitivity`)
- [x] Bootstrap intervals within and across test years (`metrics.json -> uncertainty`)
- [x] Stress tests (`metrics.json -> robustness`). Models are fitted on clean training years; only test-year inputs are corrupted, and evaluation uses true lengths and outcomes.

  | Scenario | Corruption |
  |---|---|
  | `mask_05`, `mask_10` | hide 5% / 10% of material, diameter, install year and nearby-break values |
  | `unseen_material_05` | replace 5% of materials with a value never seen in training |
  | `perturb_numeric` | install year off by up to 2 years; length off by up to 5% |

  Each method reports `capture_at_05` and its change from clean, Spearman rank correlation with the clean scores, and overlap of the 5%-budget selection. `affected_rows_confidence` shows whether corrupted rows were downgraded (LOW/MEDIUM) instead of being trusted.
- [ ] Spatial/corridor holdout, if the data supports it; otherwise list it as a limitation

## 11. Limitations

See `metrics.json -> limitations`, which is generated with the results. Key items:

- current-inventory snapshot and survivorship;
- results are conditional on breaks that link to a current, eligible pipe. Member 1 reports 508 completed main breaks with no matching pipe;
- one open-data city;
- the random baseline is a single seeded draw;
- percentiles are not probabilities;
- **tied scores** (most pipes have zero prior breaks, ages are whole years) are ordered by `segment_id` under the contract. On the 2026-10-10 data, breaking ties randomly instead changed the champion's capture@5% by at most one break per test year, so asset-ID order is not acting as a hidden predictor; and
- **the stress tests cannot hurt a history-only champion.** The prior-breaks method does not use material, diameter or install year, so its zero change under masking reflects which inputs it uses, not resilience. The lookup and logistic rows in `metrics.json -> robustness` show the real sensitivity.

## 12. Claim discipline

- **Say:** "At the same 5% network-length budget, the selected set contained X% of recorded next-year breaks versus Y% for oldest-first," with X and Y read from `metrics.json`.
- **Never say:** "prevents breaks", "saves RM...", "fully leakage-free", "works in Malaysia", or any prior-art figure as our own result.

## 13. Reproduce

Requires Python 3.11+ with `pandas`, `numpy`, `scikit-learn`, `pyarrow` and `pytest`. Member 4 owns the shared dependency file. Run from the repository root:

```bash
# tests
python -m pytest tests/modeling

# real run on Member 1's package -> artifacts/fold_predictions.parquet, artifacts/metrics.json
# and the adapted Contract A at artifacts/pipe_year.parquet (about 70 s)
python -m src.modeling.run_evaluation --member1-package data \
  --write-contract-a artifacts/pipe_year.parquet

# synthetic Contract B fixture for Members 3 and 4, plus the matching synthetic Contract A
python -m src.modeling.run_evaluation --synthetic \
  --predictions-out contracts/fixtures/fold_predictions.fixture.parquet \
  --metrics-out contracts/fixtures/metrics.example.json \
  --write-contract-a artifacts/dev/pipe_year.synthetic.parquet
```

The seed is fixed (`SEED` in `src/modeling/config.py`), so reruns reproduce the artifacts. Only `generated_at` differs between runs.
