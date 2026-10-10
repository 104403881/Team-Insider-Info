# JagaPaip — Four-Person Asynchronous Execution Plan

## Operating assumption

This plan targets a **24-hour build window** and includes optional work for a 48-hour event. Replace “Member 1–4” with names during kickoff.

The core rule is:

> **Work against contracts, not against another member's unfinished code.**

Each lane owns one module and publishes a versioned artifact. Downstream members begin immediately with a small mock artifact matching the same schema, then replace it with real output without rewriting their module.

---

## 1. Team split at a glance

| Member | Best fit | Owns | Must deliver | Must not own |
|---|---|---|---|---|
| **1 — Data & Integrity** | Strongest at Python/data/GIS | Source extraction, joins, pipe-year panel, data tests and data card | `pipe_year.parquet` plus validation report | Models, UI or slide metrics |
| **2 — ML & Evaluation** | Strongest at statistics/ML | Baselines, champion model, walk-forward testing, confidence and measured metrics | `fold_predictions.parquet` and `metrics.json` | Product consequence assumptions or UI |
| **3 — Decision Engine & Explainability** | Strongest at backend/product logic | Budget selection, archetypes, action routing, explanation templates and scenario separation | `ranked_worklists.parquet` and decision tests | Raw-data cleanup or model training |
| **4 — Product, Demo & Integration** | Strongest at frontend/storytelling | Streamlit app, Proof Mode, slides, demo script, release bundle and integration branch | Working offline demo and six-slide deck | Recalculating metrics in UI |

### Single owner rule

- Data truth: **Member 1** decides.
- Measured model/result truth: **Member 2** decides.
- Action-policy and scenario truth: **Member 3** decides.
- Demo scope and release integration: **Member 4** decides.

Anyone may review; only the owner edits that lane's files unless explicitly pairing on a blocker.

---

## 2. Proposed repository ownership

```text
contracts/                         # changes require producer + consumer approval
  pipe_year.schema.json            # Member 1
  fold_predictions.schema.json     # Member 2
  ranked_worklists.schema.json     # Member 3
  fixtures/

src/
  data/                             # Member 1 only
  modeling/                         # Member 2 only
  decision/                         # Member 3 only

app/                               # Member 4 only
slides/                            # Member 4 only
docs/
  data-card.md                      # Member 1
  model-card.md                     # Member 2
  decision-policy.md               # Member 3
  demo-script.md                    # Member 4

tests/
  data/                             # Member 1
  modeling/                         # Member 2
  decision/                         # Member 3
  app/                              # Member 4

artifacts/                          # generated handoff files; never hand-edit metrics
```

Member 4 is the **integration captain** and owns root/shared files such as `README.md`, dependency configuration and launch scripts. Other members request root-file changes in their PR description instead of editing the same shared files concurrently.

---

## 3. Thirty-minute kickoff — the only required synchronous start

Agree and write down these six decisions before splitting:

1. exact event: at least one recorded break in the next calendar year;
2. primary decision metric: capture within the top 5% of network length;
3. planning budgets shown: 1%, 2%, 5% and 10% of network length;
4. baseline methods: random, oldest-first and previous-break-only;
5. field names and types in the three contracts below; and
6. one frozen demo year plus two backup years.

At minute 30, every member starts their first task. Do not hold a long architecture meeting.

---

## 4. Shared contracts

These contracts are the key to asynchronous work. Freeze version `1.0` during kickoff.

### Contract A — Data → Modeling

**File:** `artifacts/pipe_year.parquet`  
**Owner:** Member 1  
**Consumers:** Members 2 and 3

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `segment_id` | string | yes | Stable pipe identifier |
| `score_year` | integer | yes | Year being forecast |
| `install_year` | integer/null | yes | Installation year from source snapshot |
| `age_years` | float/null | yes | `score_year - install_year`, never current age |
| `material` | string | yes | Normalized value; unknown becomes `UNKNOWN` |
| `diameter_mm` | float/null | yes | Pipe diameter if available |
| `length_m` | float | yes | Positive segment length |
| `prior_break_count` | integer | yes | Breaks strictly before 1 January `score_year` |
| `years_since_last_break` | float/null | yes | Point-in-time history only |
| `nearby_prior_breaks` | integer/null | no | Spatial feature using prior events only |
| `is_ambiguous_history` | boolean | yes | Replacement/impossible-date concern |
| `data_quality_flags` | string | yes | JSON array encoded as text |
| `geometry_wkt` | string/null | no | Geometry for display, not required by model |
| `target_next_year_break` | integer | yes | 0/1 outcome during `score_year` |
| `source_snapshot_date` | date/string | yes | Data provenance |

**Contract tests:**

- unique key is `(segment_id, score_year)`;
- target is only 0 or 1;
- `prior_break_count >= 0`;
- `length_m > 0`;
- `age_years >= 0`, otherwise the row is flagged ambiguous and excluded from the primary panel;
- no history-derived feature uses a date on/after the score date;
- ambiguous histories are flagged rather than silently corrected; and
- condition score or known post-outcome fields are absent.

### Contract B — Modeling → Decision/UI

**File:** `artifacts/fold_predictions.parquet`  
**Owner:** Member 2  
**Consumers:** Members 3 and 4

Use long format: one row per segment, test year and method.

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `segment_id` | string | yes | Joins to Contract A |
| `test_year` | integer | yes | Historical Proof Mode year |
| `method` | string | yes | `random`, `oldest`, `prior_breaks`, `champion` |
| `model_score` | float | yes | Raw ranking score |
| `risk_percentile` | float | yes | 0–1, larger means higher risk |
| `confidence_label` | string | yes | `HIGH`, `MEDIUM`, `LOW` |
| `is_ood` | boolean | yes | Unfamiliar/data-poor record |
| `actual_break` | integer | yes | Hidden until Proof Mode reveal |
| `length_m` | float | yes | Equal-budget selection unit |

**File:** `artifacts/metrics.json`  
**Owner:** Member 2

It must contain:

```json
{
  "schema_version": "1.0",
  "generated_at": "ISO-8601 timestamp",
  "data_snapshot": "source date",
  "selection_unit": "network_length_fraction",
  "champion_method": "measured winner",
  "champion_selection_rule": "highest mean capture_at_05; ties go to the simpler method",
  "test_years": [2021, 2022, 2023],
  "budgets": [0.01, 0.02, 0.05, 0.10],
  "methods": {
    "oldest": {
      "capture_at_05": 0.0,
      "precision_at_05": 0.0,
      "observed_non_events_at_05": 0
    }
  },
  "by_year": {
    "2023": {
      "budget_0.05": {
        "champion": {
          "selected_length_m": 0.0,
          "breaks_captured": 0,
          "capture": 0.0
        }
      }
    }
  },
  "limitations": []
}
```

The values above are schema examples, not desired results. Equal-budget selection is defined by sorting Contract B on `risk_percentile` and accumulating `length_m` until the requested network-length fraction is reached. Member 4 must never type or recalculate measured result numbers in UI or slides; Proof Mode reads the aggregate and per-year values from this artifact.

### Contract C — Decision Engine → Product

**File:** `artifacts/ranked_worklists.parquet`  
**Owner:** Member 3  
**Consumer:** Member 4

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `test_year` | integer | yes | Historical or current planning year |
| `method` | string | yes | Allows side-by-side baseline comparison |
| `ranking_mode` | string | yes | `VALIDATED_RISK` or `SCENARIO_CONSEQUENCE` |
| `segment_id` | string | yes | Ranked candidate segment |
| `priority_rank` | integer | yes | Deterministic order within year/method |
| `cumulative_length_m` | float | yes | Lets UI apply the budget slider |
| `risk_percentile` | float | yes | Model evidence |
| `risk_pattern` | string | yes | Descriptive, never causal |
| `confidence_label` | string | yes | Spend-confidence/action input |
| `consequence_index` | float | yes | Assumption; visibly labelled |
| `recommended_action` | string | yes | `MONITOR`, `INSPECT`, `RENEWAL_REVIEW` |
| `reason_short` | string | yes | Plain-language evidence template |
| `actual_break` | integer | yes | UI hides until reveal |
| `geometry_wkt` | string/null | no | Map support |

Contract C contains **all eligible candidates in ranked order**, not only a preselected budget slice, so the UI can filter by `cumulative_length_m` without rerunning decision logic. `VALIDATED_RISK` rows must preserve Contract B's risk ordering and power Proof Mode. `SCENARIO_CONSEQUENCE` rows are optional and must remain visibly assumption-based.

**Decision tests:**

- cumulative selected length never exceeds the chosen budget;
- the same input always produces the same order;
- `VALIDATED_RISK` ordering and per-year Proof Mode counts exactly match Contract B and `metrics.json`;
- consequence inputs never change `VALIDATED_RISK` rows or measured metrics;
- low-confidence/OOD rows never receive automatic `RENEWAL_REVIEW`;
- risk patterns contain no causal language; and
- scenario calculations remain in a separately labelled payload/panel.

### Contract-change rule

After version `1.0` is frozen:

- adding an optional field requires producer and consumer approval;
- renaming, removing or changing a type requires a schema version bump;
- after the H8 vertical-slice gate, make adapters rather than breaking contracts; and
- announce every change in the team channel with old field, new field and migration owner.

---

## 5. Member 1 — Data & Integrity

### Mission

Produce the smallest trustworthy point-in-time dataset that supports a real historical test.

### Start immediately with

1. create Contract A and a 50–100-row development fixture;
2. probe both Kitchener ArcGIS sources;
3. verify `ASSETID → WATMAINID` on manual samples;
4. profile duplicates, missing material/length and pre-install-date breaks; and
5. build one test year end to end before expanding all years.

### Deliverables

- reproducible source download/cache;
- normalized mains and break tables;
- leakage-controlled `pipe_year.parquet`;
- join and quality report;
- tests for keys, dates, target construction and forbidden fields;
- `docs/data-card.md` covering source dates, exclusions, ambiguity and survivorship; and
- one small committed fixture so every other lane works offline.

### Definition of done

- another member can generate Contract A with one documented command;
- one historical row can be traced back to source records;
- features for year `Y` contain no break at/on/after 1 January `Y`;
- impossible/ambiguous histories are reported and sensitivity-ready; and
- Member 2's contract validator accepts the file.

### After the H8 handoff

Member 1 becomes data QA/support: investigate anomalies, freeze the data snapshot, review factual data claims and help Member 4 create a small provenance panel. Do not start a second model.

---

## 6. Member 2 — ML & Evaluation

### Mission

Determine which ranking method actually wins out of time and produce every measured number shown to judges.

### Start immediately with

1. generate/use the Contract A fixture;
2. implement a year-based walk-forward splitter;
3. implement capture-at-network-budget and precision-at-budget;
4. create deterministic random, oldest-first and prior-break baselines; and
5. make Contract B using dummy scores so Members 3 and 4 are unblocked.

### Deliverables

- baseline ladder: random, oldest, prior breaks, smoothed lookup;
- regularized logistic hazard model;
- optional boosted-tree challenger only if time permits;
- fold predictions for every method;
- metrics at 1%, 2%, 5% and 10% length budgets;
- PR-AUC and calibration diagnostics where appropriate;
- variation/confidence interval across test years;
- missingness/OOD stress-test results;
- `metrics.json`; and
- `docs/model-card.md` with champion choice and limitations.

### Definition of done

- no random row split exists in result-generating code;
- every score is produced using only prior-year information;
- baselines receive exactly the same length budget;
- rerunning with a fixed seed reproduces artifacts;
- prior-art figures are not copied into measured outputs; and
- Member 3's contract validator accepts Contract B.

### Freeze rule

At H12, select the measured champion. If a lookup beats gradient boosting, ship the lookup. After freeze, only fix correctness bugs—do not tune until the demo breaks.

### After the H12 handoff

Member 2 owns result integrity, the model-card slide and technical judge answers. Help Proof Mode verification, not UI styling.

---

## 7. Member 3 — Decision Engine & Explainability

### Mission

Turn risk scores into a bounded, safe and understandable utility worklist.

### Start immediately with

1. use Member 1's Contract A fixture and Member 2's Contract B fixture;
2. if official fixtures are not yet published, use local uncommitted mocks from the frozen schemas rather than creating competing shared fixtures;
3. implement the `(segment_id, score_year/test_year)` join needed for risk patterns and explanations;
4. implement deterministic selection under a length budget;
5. define five descriptive risk-pattern rules and confidence-to-action routing; and
6. publish the official Contract C fixture early so Member 4 can build the real UI shape.

### Deliverables

- risk-pattern assignment: repeat-break, material/cohort, spatial-cluster, age-led, data-poor;
- consequence configuration with explicit assumption labels;
- value-per-cost ranking and budget selection;
- `MONITOR`, `INSPECT`, `RENEWAL_REVIEW` policy;
- plain-language explanation templates;
- ranked worklists for champion and baselines in `VALIDATED_RISK` mode;
- an optional, separately labelled `SCENARIO_CONSEQUENCE` worklist;
- decision unit/contract tests; and
- `docs/decision-policy.md`.

### Definition of done

- any capacity setting returns a deterministic in-budget list;
- low-confidence/OOD records route to evidence gathering, not capital commitment;
- every selected row has a category, reason and action;
- no category is described as a physical root cause;
- measured targeting and scenario savings are impossible to confuse in the output; and
- Member 4 can render Contract C without importing model-training code.

### After the H16 handoff

Member 3 becomes integration QA: test edge cases in the budget slider, explanation cards and assumption wall; produce a frozen offline bundle for demo backup.

---

## 8. Member 4 — Product, Demo & Integration

### Mission

Make the decision and its proof understandable within three minutes, while keeping the app independent of live services.

### Start immediately with

1. build the Streamlit page shell using Member 3's Contract C fixture, or a local uncommitted mock until it arrives;
2. implement the capacity slider and ranked table;
3. build the segment evidence-card component;
4. implement the hide/decide/reveal state for Proof Mode; and
5. draft the six slide headings and 180-second narration.

### Deliverables

- worklist screen;
- evidence card showing risk pattern, confidence, action and reason;
- Proof Mode year selector and reveal interaction;
- side-by-side champion versus oldest-first counters;
- multi-budget performance chart read from `metrics.json`;
- visibly separated validated-results and scenario panels;
- graceful loading/error/empty states;
- offline cached demo bundle;
- six-slide deck, timed script and backup recording/screenshots; and
- one-command launch instructions.

### Integration-captain duties

- maintain the integration branch;
- own shared dependency/config files;
- merge only contract-valid artifacts;
- run the end-to-end smoke test after each gate;
- keep `main` stable until the team approves the release; and
- reject hardcoded metrics, copied prior-art claims or unlabelled Malaysian-performance claims.

**Load relief:** Member 2 is deputy integrator for the H8 and H12 gates. Member 2 runs contract checks and end-to-end smoke tests and may merge artifact-only handoffs into `integration`. Member 4 remains the sole resolver for shared configuration conflicts and owns the final release decision.

### Definition of done

- app starts without internet access;
- changing the budget changes the list without retraining;
- reveal stays hidden until the presenter clicks it;
- all displayed measured values come from generated artifacts;
- the app remains usable without the map; and
- a teammate who did not build the UI can complete the demo from the script.

---

## 9. Dependency graph and how nobody waits

```text
Member 1: real Contract A ─────┬──► Member 2: real Contract B ──► Member 3: real Contract C ──► Member 4: release
                               └────────────────────────────────► Member 3

Kickoff fixtures follow the same A → B → C interfaces, so implementation starts before real artifacts arrive.
```

| Member | Real dependency | Work before dependency arrives |
|---|---|---|
| 1 | Raw source availability | Contract, cache layer, source profiler and tests |
| 2 | Real Contract A | Walk-forward framework, metrics and baselines on fixture A |
| 3 | Real Contracts A and B | Join, budget selector, action rules and explanations on fixtures A/B |
| 4 | Real Contract C and `metrics.json` | Complete UI flow, Proof Mode and slides on fixture C/example metrics |

No one sends “waiting for X.” They continue against the agreed fixture and report the blocked integration separately. After G2, replacing fixture data with real artifacts must be a **data-only swap through the frozen interfaces**; if a producer discovers a mismatch, they supply an adapter rather than forcing downstream rewrites.

---

## 10. Integration gates

### G0 — H0:30: contracts frozen

- event, metrics, budgets and schemas agreed;
- every member has a branch and first ticket;
- fixture ownership assigned.

### G1 — H4: data go/no-go

Required:

- sources load;
- join is manually verified;
- one valid pipe-year fold exists on a verified subset;
- random and oldest-first run once on that subset; and
- major snapshot/ambiguity risks are known.

G1 is a feasibility decision, **not the production Contract A handoff**. If it fails, narrow to a verified subset immediately. Do not polish maps.

### G2 — H8: production Contract A + ugly vertical slice

Required end-to-end flow:

```text
real pipe-year rows → one baseline score → one worklist → one UI table
```

- Member 1 publishes production Contract A and its validation report;
- all fixture-to-real replacements pass without interface changes;
- Member 2 acts as deputy integrator for this gate, runs the end-to-end smoke test and reports failures while Member 4 continues the UI; and
- Member 4 retains final authority over shared configuration and integration conflicts.

It may look bad. It must be real and repeatable.

### G3 — H12: data/model/result freeze

- data snapshot frozen;
- champion selected using the rule recorded in `metrics.json`;
- multi-year and per-year Proof Mode metrics generated;
- `metrics.json` frozen except correctness fixes;
- Member 2 runs the H12 end-to-end smoke test as deputy integrator; and
- exact slide result wording approved by Members 1 and 2.

### G4 — H16: feature freeze

- action routing and explanations integrated;
- Proof Mode works with a real historical year;
- Proof Mode ordering and counters match Contract B and the per-year values in `metrics.json`;
- consequence/scenario panel clearly separated; and
- no new product features accepted.

### G5 — H20: release candidate

- full three-minute rehearsal;
- offline run tested on presentation laptop;
- backup year, screenshots and video prepared;
- every number traced to `metrics.json`; and
- likely judge questions assigned.

### G6 — H22–H24: demo freeze

Only fix blockers. Rehearse, simplify and preserve a known-good release.

### If the event lasts 48 hours

Treat H24 as a complete submission. Use the second day only for, in order:

1. spatial/corridor validation;
2. better confidence intervals and robustness evidence;
3. map polish;
4. Malaysian import-schema screen;
5. scenario sensitivity chart; and
6. visual polish.

Do not restart model selection or rewrite contracts.

---

## 11. Git and handoff protocol

### Branches

```text
feat/data-pipeline             # Member 1
feat/model-evaluation          # Member 2
feat/decision-engine           # Member 3
feat/product-demo              # Member 4
integration                    # Member 4 merges here
main                           # stable, release only
```

### Every handoff/PR must state

```text
Contract version:
Command to reproduce:
Inputs:
Outputs:
Tests run:
Known limitations:
Downstream action required:
```

### Merge rules

- small vertical PRs are better than one final dump;
- producer and direct consumer review contract changes;
- never commit secrets or depend on a live API during the demo;
- cache only data permitted by source terms;
- stage specific files rather than unrelated changes;
- do not force-push shared branches; and
- do not merge experimental work after its freeze gate.

---

## 12. Asynchronous communication protocol

Use one pinned team channel/thread. Post at each gate or at least every two hours:

```text
[Member / Hour]
DONE: concrete artifact or commit
NEXT: next deliverable
BLOCKER: one sentence, owner needed, deadline
CONTRACT CHANGE: none / exact proposed change
DEMO IMPACT: none / what changes for presenter
```

Rules:

- a blocker must name the person who can resolve it;
- if unanswered for 20 minutes, continue with the fixture/adapter;
- decisions affecting claims or contracts are written, not left in voice chat;
- urgent means it blocks the next integration gate, not merely “I would prefer feedback”; and
- use short gate calls of at most 10 minutes instead of staying in a permanent call.

---

## 13. First 90 minutes — exact parallel tickets

### Member 1

- publish Contract A schema and fixture;
- retrieve both source samples;
- validate ten break-to-main joins manually;
- report field names and first data risks.

### Member 2

- implement `capture_at_budget` and a walk-forward split test;
- generate dummy Contract B;
- prove oldest/random comparisons use equal network length.

### Member 3

- implement budget selection on 20 dummy segments;
- write the action-routing truth table;
- generate dummy Contract C with five explanation examples.

### Member 4

- render dummy Contract C in Streamlit;
- make the budget slider filter by cumulative length;
- implement hidden/revealed outcomes;
- draft the opening and closing lines.

At H1:30, exchange artifacts—do not present slide updates.

---

## 14. Failure and scope-cut order

| Failure | Deadline | Action |
|---|---:|---|
| Raw join is unreliable | H4 | Use a manually verified subset; preserve disclosure and time-travel test |
| Champion model does not beat simple lookup | H12 | Ship the lookup as champion; do not hide the result |
| Consequence data is weak | H14 | Use risk-only validated ordering; keep consequence as disabled scenario input |
| Map is unstable | H16 | Drop it; use ranked table and evidence card |
| Live calculations are slow | H18 | Precompute all demo-year/budget artifacts |
| Integration remains unstable | H20 | Use frozen offline bundle and record backup video |
| Slides and app disagree | Any | `metrics.json` wins; correct the slide |

Cut in this order:

1. boosted-tree model;
2. live map;
3. continuous scenario sliders;
4. spatial holdout panel;
5. extra animations;
6. current-year prediction mode.

Never cut:

- oldest/random baselines;
- temporal Proof Mode;
- equal-budget comparison;
- action list and explanation;
- data/model limitations; or
- validated-versus-scenario separation.

---

## 15. Final sign-off matrix

| Area | Signs off | Question answered |
|---|---|---|
| Data lineage and historical validity | Member 1 | “Can every feature be justified at score time?” |
| Metrics and model claims | Member 2 | “Was this number generated out of time and against the same budget?” |
| Actions, assumptions and safety | Member 3 | “Does confidence lead to an appropriate human-reviewed action?” |
| Demo, slides and release | Member 4 | “Can judges understand and reproduce the story in three minutes?” |
| Final submission | All four | “Are we claiming only what the evidence proves?” |

---

## 16. One-line individual briefs

Copy these into four issues:

- **Member 1:** “Deliver a traceable, leakage-controlled pipe-year dataset and data card; pass the H4 feasibility gate and publish production Contract A by H8.”
- **Member 2:** “Deliver reproducible walk-forward predictions and same-budget metrics; freeze the honest champion and Contract B by H12.”
- **Member 3:** “Turn scores into deterministic in-budget actions and explanations; freeze Contract C by H16.”
- **Member 4:** “Render contracts into a reliable offline Proof Mode, integrate releases and deliver the three-minute pitch by H20.”

The team succeeds when each member can work alone for two hours, exchange only a contract-valid artifact, and have the complete product improve without a coordination meeting.
