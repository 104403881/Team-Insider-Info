# JagaPaip

> **Know which pipe first.**  
> The decision layer for Malaysia's water infrastructure.

## Recommendation

Build **JagaPaip**, a budget-aware water-pipe intervention planner for utility asset managers.

JagaPaip forecasts which pipe segments are most likely to break in the next 12 months, describes each segment's **risk pattern**, combines risk with consequence and confidence, and turns a fixed budget into an explainable **monitor / inspect / renewal-review** worklist.

The product is not another risk map. Its core output is a defensible answer to one decision:

> **Given this year's limited budget, which pipe segments should we act on first, and why?**

The open-data MVP will be trained and tested on City of Kitchener pipe and break records. It must be presented as a **method demonstrator**, not evidence that the same model already works in Malaysia. A Malaysian deployment requires a retrospective pilot using a participating utility's GIS asset register and work-order history.

No idea guarantees a win. This one is unusually well aligned with the brief because the team can show a meaningful prediction, named issue types, a constrained action decision, false-alarm cost, understandable reasons, and an honest historical test of whether the recommendation was better.

---

## 1. What the hackathon brief actually rewards

The three repository images require much more than model accuracy.

| Brief requirement | What JagaPaip must show | Proof on demo day |
|---|---|---|
| **Detect** | Forecast at least one recorded break on a pipe segment in the next 12 months | Leakage-controlled walk-forward predictions |
| **Categorize** | Label the descriptive risk pattern, not merely “anomaly” | Repeat-break, material/cohort, spatial-cluster, or data-poor pattern |
| **Prioritize** | Decide what fits within a fixed inspection/renewal budget | Ordered worklist and budget allocation |
| **Explain** | Give a non-technical reason and appropriate action | Evidence card for every selected segment |
| Specific problem and user | Utility asset manager deciding an annual programme | One named workflow, not a generic dashboard |
| Robustness | Handle missing, unknown, noisy, and changing records | Missingness/OOD stress test and confidence flag |
| Minimize false alarms | Cap workload and avoid expensive action on weak evidence | Precision and selected-without-next-year-break count at the operating budget |
| Recommendations | Route each result to monitor, inspect, or renewal review | Action policy shown in the UI |
| Measurable impact | Beat credible targeting baselines at the same budget | Historical “hide, decide, reveal” test |

**Core judging answer:** JagaPaip helps an asset manager choose a better set of pipes under the same resource constraint, and tests that claim against what broke next.

---

## 2. Why Malaysia, and why now

The local story is a scarcity-of-capital problem, not simply a technology problem.

The Edge Malaysia reported in April 2025, citing PAAB and the SPAN Water and Sewerage Fact Book 2023, that:

- non-revenue water (NRW) in Peninsular Malaysia and Labuan was **37.1% in 2023**, versus a **28% target by 2030**;
- there were **39,752 km of asbestos-cement pipe**;
- replacing that AC network was estimated at about **RM35.8 billion**, while state operators had earmarked about **RM1.87 billion**; and
- slow leaks, rather than bursts alone, were described as the primary NRW cause.

That last point is important. **Do not claim that predicting breaks solves all NRW.** NRW also includes slow leakage, metering and commercial losses. JagaPaip's first validated event is a recorded pipe break, making it an infrastructure-renewal prioritization wedge. A later local pilot can add district-metered-area flow, pressure, acoustic, soil and rainfall signals to address slow leaks.

The immediate buyer is a SPAN-regulated state water operator's capital-planning or asset-management function. The daily user is the network/asset manager who must justify why one segment is inspected or reviewed before another.

Source: [The Edge Malaysia, “Improving NRW a priority, but higher tariffs also needed to sustain the water industry,” April 2025](https://theedgemalaysia.com/node/751568).

---

## 3. The pitch

### One sentence

**JagaPaip turns a utility's existing asset and break records into a budget-bounded, explainable action list so it can investigate or renew the right kilometre first.**

### 15 seconds

> Malaysia cannot replace every ageing pipe at once. JagaPaip predicts which segments are most likely to fail, shows the risk pattern and consequence, and converts any fixed budget into an explainable monitor, inspect, or renewal-review list. Then we time-travel through historical data to prove whether it selected more of the pipes that actually broke than oldest-first planning.

### Closing line

> **Do not replace every old pipe. Know which pipe first.**

---

## 4. Product workflow

1. The asset manager selects a planning year and available inspection capacity in kilometres or budget units.
2. JagaPaip generates next-12-month break-risk ranks for all eligible segments.
3. Each segment receives a **descriptive, non-causal risk pattern** and a confidence level.
4. A decision engine creates a feasible worklist within the selected budget.
5. The user clicks a segment to see evidence, uncertainty, consequence assumptions and the recommended next action.
6. In **Proof Mode**, JagaPaip hides a historical year's outcomes, makes the plan, and then reveals which segments actually broke.

### The one screen that must ship

The main screen should contain:

- a budget/capacity slider;
- a ranked worklist with action, risk pattern and confidence;
- a map if time permits, but a reliable table is more important;
- one plain-language evidence card; and
- side-by-side “validated performance” and “scenario impact” panels that cannot be confused.

---

## 5. Detect, Categorize, Prioritize, Explain

### Detect

**Prediction unit:** pipe segment × planning year.  
**Target:** at least one recorded break in `[1 January year, 1 January next year)`.  
**Horizon:** next 12 months.  
**Output:** risk score/risk percentile; calibrated probability only if calibration is demonstrably adequate.

### Categorize

Use categories that describe observed evidence without pretending to diagnose physical causation:

| Risk pattern | Evidence | Safe wording |
|---|---|---|
| **Repeat-break pattern** | One or more breaks strictly before the scoring date | “Previous breaks increase observed recurrence risk.” |
| **Material/cohort pattern** | Material and installation cohort have elevated historical rates | “This material/cohort group has broken more often historically.” |
| **Spatial-cluster pattern** | Nearby eligible segments had prior breaks | “This segment lies near a historical break cluster.” |
| **Age-led pattern** | Age contributes most, without stronger history | “Age is the main available risk signal.” |
| **Data-poor / unfamiliar** | Missing fields, unseen material, or weak comparison group | “Evidence is limited; inspect before committing capital.” |

Never label these “root causes.” They are communication archetypes.

### Prioritize

Keep validated targeting separate from utility-defined consequence assumptions.

For the core backtest, rank by model score and measure breaks captured under a fixed percentage of network length. For the product worklist:

```text
RiskValue_i = RiskPercentile_i × ConsequenceIndex_i
SelectionDensity_i,a = RiskValue_i / ActionCost_i,a
```

The optimiser selects segment/action pairs while:

```text
sum(ActionCost_i,a) <= AvailableBudget
at most one action is selected per segment
```

- **RiskPercentile** comes from the model.
- **ConsequenceIndex** is utility-configurable and must be labelled as an assumption until local outcome data validates it. Possible inputs are diameter, road class, estimated customers affected and proximity to critical facilities.
- Segment length belongs in inspection/action cost, not automatically in consequence; otherwise risk may be double-counted.
- Confidence controls the action type rather than being hidden inside the score.

A greedy value-per-cost selector is enough for the MVP. A knapsack solver is an optional enhancement.

### Explain

Example evidence card:

> **Inspect first — high risk, medium confidence.** This 1958 cast-iron segment is in a material/cohort group with an elevated historical break rate and has two earlier recorded breaks. The recommendation is inspection, not replacement, because its comparison group is small. If inspection confirms deterioration, escalate it for renewal review.

Show:

- rank and comparison with network baseline;
- top 2–3 contributing facts;
- data-quality/confidence flag;
- consequence inputs and whether they are measured or assumed;
- recommended action and why that action matches the confidence; and
- a “what would lower this priority?” counterfactual where feasible.

### Action policy

| Risk/consequence | Confidence | Recommendation |
|---|---:|---|
| High | High | Place on **renewal review** list; engineering approval remains required |
| High | Low/medium | **Inspect** using the utility's approved diagnostic process |
| Medium | Any | **Monitor** or bundle with nearby scheduled work |
| Low | Any | No action this cycle |

The model never autonomously orders excavation or replacement.

---

## 6. Data plan and evidence boundary

### Open-data demonstrator

Use the raw municipal sources:

- [City of Kitchener Water Main Breaks](https://open-kitchenergis.opendata.arcgis.com/datasets/KitchenerGIS::water-main-breaks/about)
- [City of Kitchener Water Mains](https://open-kitchenergis.opendata.arcgis.com/datasets/KitchenerGIS::water-mains/about)
- Optional historical climate context: [Environment and Climate Change Canada](https://climate.weather.gc.ca/)

A current public Kitchener project documents approximately **16,208 mains, 2,925 confirmed breaks and 340,150 pipe-year rows with a 0.554% positive rate**. It reports ten-year walk-forward capture@5% of 0.301 for a simple material/cohort/prior-break lookup, 0.106 for age-only and 0.052 for random selection.

Those numbers are **prior-art feasibility evidence and reproduction targets, not this team's results**. Do not put them on a results slide unless clearly marked as external. The team must extract the municipal data, rebuild the panel and report its own measured values.

Prior-art reference: [js3lliott/water-main-break-prediction-KW](https://github.com/js3lliott/water-main-break-prediction-KW). Check its licence before reusing any code or assets. Prefer an independent implementation from the raw municipal sources.

### Four-hour go/no-go gate

Within the first four build hours, require all of the following:

1. both source datasets load reliably;
2. break-to-main linkage is understood and sampled manually;
3. a pipe-year table is generated;
4. event counts and impossible dates are profiled;
5. a random and oldest-first baseline run end to end; and
6. at least one historical fold produces a result artifact consumed by the UI.

The documented Kitchener linkage is `ASSETID → WATMAINID`. Do not use a many-to-many road-segment join. Verify this independently against sampled records.

If this gate fails, fix or narrow the data before building a polished interface. Do not spend half the hackathon on the map while the label join is uncertain.

### Core table

```text
pipe_year
- segment_id
- score_date
- installation_year
- material
- diameter
- segment_length
- prior_break_count       # break_date < score_date only
- years_since_last_break  # as of score_date only
- nearby_prior_breaks     # only events before score_date
- data_quality_flags
- target_next_year_break
```

### Malaysia boundary

No public Malaysian segment-level asset-plus-break-history dataset was found during concept research. Therefore:

- do not train a “Malaysian” model on invented records;
- label the app **Open-data proof mode — Kitchener**;
- describe Malaysian performance as untested until a utility retrospective pilot;
- provide a CSV/schema adapter showing what a local operator would supply; and
- use Malaysian aggregate facts only for market/problem framing, not model validation.

This honesty is an advantage, not an apology.

---

## 7. Model strategy

This is a rare-event tabular ranking problem. Deep learning is unnecessary and likely harder to defend.

### Baseline/challenger ladder

1. random selection;
2. oldest-pipe-first;
3. previous-break-count-only;
4. smoothed material × installation-cohort × prior-break lookup;
5. regularised logistic discrete-time hazard model;
6. optional gradient-boosted trees.

Promote the simplest method that wins consistently in walk-forward testing. If the lookup beats gradient boosting, **ship the lookup** and explain why. The intelligence of JagaPaip is also in verified feature timing, uncertainty-aware action routing and budget optimisation—not in choosing the most complex model.

### Feature rules

Safe or relatively stable candidates:

- installation cohort and age at score date;
- material;
- diameter;
- segment length as exposure/cost, treated carefully;
- breaks strictly before score date;
- time since previous break;
- nearby breaks strictly before score date; and
- historical weather summaries known by score date, only if they improve testing.

Never use:

- next-year weather;
- break records on or after the score date;
- a current `condition_score` influenced by later failures;
- post-repair attributes as if they existed before replacement;
- full-dataset encodings or imputation fitted before splitting; or
- consequence fields as target proxies.

### Calibration and uncertainty

- Optimise ranking metrics first.
- Use out-of-fold isotonic or Platt calibration only if there are enough positives.
- If calibration is poor, show a **risk percentile**, not a fake precise probability.
- Use bootstrap intervals or fold variation for performance.
- For lookup groups, smooth sparse rates and flag low-support groups.
- Unknown materials or out-of-range records receive an OOD/data-poor flag and are routed to inspection rather than renewal review.

---

## 8. Leakage and bias controls

The public source is a current inventory snapshot, so a perfectly historical asset reconstruction may be impossible. Do **not** say “zero leakage” or “fully leakage-free.” Say **leakage-controlled evaluation with disclosed snapshot limitations**.

Required controls:

1. all history-derived features use events strictly before the fold's score date;
2. preprocessing and category encodings are fitted inside each training fold;
3. current condition score is excluded;
4. break events are deduplicated and impossible pre-install-date records are isolated;
5. records suggesting asset replacement are not silently attributed to the current pipe;
6. ambiguous rows are excluded in a sensitivity analysis;
7. current surviving assets are not presented as a complete historical inventory; and
8. survivorship bias is stated: repeatedly failing pipes may have been replaced and disappeared from the current network.

Report a sensitivity comparison with and without ambiguous asset histories. A spatial/corridor holdout is desirable if geography and event counts support it. Otherwise explicitly list spatial correlation as a residual limitation.

---

## 9. Validation: prove a better decision

### Historical time-travel protocol

For each test year `Y`:

1. use only information available before 1 January `Y`;
2. train or estimate risk using earlier years;
3. score eligible segments for year `Y`;
4. select the top worklist under the same network-kilometre budget for every method;
5. reveal recorded breaks during `Y`; and
6. compare JagaPaip with oldest-first, prior-break-only and random targeting.

Repeat across multiple years. Do not use a random row split.

### Primary metric

**Capture@5%-of-network-length:** the share of all next-year breaks that occur in the selected 5% of network kilometres.

Also show the budget curve at 1%, 2%, 5% and 10%, because one operating point can be misleading.

### Secondary metrics

- lift over random and oldest-first at the same kilometre budget;
- precision among selected segments;
- number of selected segments without a recorded next-year break;
- false selections per captured break;
- PR-AUC, not accuracy, as a model diagnostic;
- calibration error/reliability plot if probabilities are displayed; and
- variation or bootstrap confidence interval across years.

Use careful wording: a selected segment without a break next year is an observed non-event, not proof that inspection was useless; it could still contain deterioration or fail later.

### Robustness tests

- randomly mask 5% and 10% of non-critical feature values and measure ranking stability;
- map unseen materials to `UNKNOWN` and verify graceful handling;
- perturb numeric fields within plausible measurement tolerances;
- compare temporal results with a spatial/corridor holdout if feasible; and
- display an abstention/data-poor state rather than silently imputing high confidence.

### Results table to fill only after running

| Method | Selected km | Actual next-year breaks in selection | Capture@5% | Precision@5% | Observed non-events | Lift vs oldest-first |
|---|---:|---:|---:|---:|---:|---:|
| Random | `[measured]` | `[measured]` | `[measured]` | `[measured]` | `[measured]` | `[measured]` |
| Oldest first | `[measured]` | `[measured]` | `[measured]` | `[measured]` | `[measured]` | `1.00×` |
| Prior-break only | `[measured]` | `[measured]` | `[measured]` | `[measured]` | `[measured]` | `[measured]` |
| JagaPaip champion | `[measured]` | `[measured]` | `[measured]` | `[measured]` | `[measured]` | `[measured]` |

**Never hardcode desired values into the app.** Generate a versioned `metrics.json` from the evaluation pipeline and make the UI read it.

---

## 10. Impact without fake ROI

Keep two visibly separate panels.

### Validated performance

This panel may state only what the historical test measures, for example:

> “At the same 5% network-length budget, JagaPaip's selected set contained X% of recorded next-year breaks versus Y% for oldest-first.”

That proves **targeting quality**, not breaks prevented.

### Scenario impact — assumptions

Let the user vary:

- cost per kilometre inspected;
- planned intervention cost;
- emergency break cost;
- intervention effectiveness; and
- consequence multiplier for critical locations.

A transparent scenario can calculate:

```text
Scenario net value
= selected historical break exposure
  × assumed intervention effectiveness
  × assumed avoidable incident cost
  - assumed inspection/intervention programme cost
```

Show ranges and the break-even intervention effectiveness. Label every output **scenario, not measured causal impact**. Replace example assumptions with utility-provided values in a Malaysian pilot.

---

## 11. The winning three-minute demo

### 0:00–0:25 — Malaysia and the one decision

Show the gap: replacing all vulnerable pipe is unaffordable. Say:

> “The question is not whether old pipes are risky. The question is which kilometre earns the next ringgit.”

Immediately acknowledge that breaks are one part of NRW and define the MVP's exact target.

### 0:25–0:55 — Set the constraint

Open **Proof Mode**, choose a historical year and set the same 5% network-length budget for JagaPaip and oldest-first. Actual outcomes remain hidden.

### 0:55–1:30 — Produce an action list

Move the capacity slider. The worklist changes live. Click one segment and show:

- detected next-year break risk;
- descriptive risk pattern;
- priority/consequence;
- confidence/data quality;
- plain-language evidence; and
- monitor, inspect or renewal-review action.

Highlight one high-risk but low-confidence segment routed to **inspect**, demonstrating false-alarm discipline.

### 1:30–2:15 — The reveal

Press **Reveal next year**. Actual break locations appear. Two counters animate side by side:

- breaks contained in JagaPaip's selected kilometres; and
- breaks contained in oldest-first's selected kilometres.

Then show the multi-year budget-capture curve and uncertainty interval. This is the memorable proof moment.

### 2:15–2:40 — Honesty wall

Point to the separate scenario tab:

> “The targeting result is measured. Savings are assumptions until a utility pilot measures intervention outcomes.”

### 2:40–3:00 — The next big thing

Show the roadmap from one open-data demonstrator to a Malaysian utility pilot, then slow-leak sensor fusion and a common national infrastructure decision layer.

Close with:

> **“JagaPaip does not ask Malaysia to replace every old pipe. It helps us know which pipe first.”**

---

## 12. Six-slide pitch deck

1. **Malaysia cannot replace everything** — 37.1% NRW context, AC-pipe capital gap, and the exact “which pipe first?” decision. State that breaks are only one NRW component.
2. **Meet JagaPaip** — Detect, Categorize, Prioritize, Explain, all ending in one constrained worklist.
3. **Built for trust** — point-in-time feature rules, interpretable champion/challenger model, confidence and human approval.
4. **Proof, not promises** — historical hide/decide/reveal comparison at equal budget; show only team-reproduced metrics.
5. **From score to action** — budget slider, evidence card, action routing, validated-versus-scenario wall.
6. **The next infrastructure decision layer** — local retrospective pilot, sensor-enabled leak layer, then multi-utility scale; finish with the ask for a data/pilot partner.

Do not spend a slide listing algorithms.

---

## 13. Why this is “the next big thing” without hand-waving

The large idea is not a single break classifier. It is a reusable **capital-allocation decision layer** for infrastructure.

Its credible adoption wedge is small:

- start with CSV/GIS and work-order data a utility already owns;
- make one annual planning decision better;
- record inspection outcomes to create a data flywheel; and
- add live sensors only where their information value justifies the cost.

### Roadmap

**Stage 0 — hackathon:** Kitchener open-data demonstrator, historical targeting proof and one real worklist screen.

**Stage 1 — Malaysian pilot:** one operator supplies de-identified asset and work-order history; rebuild locally, run a retrospective test, agree consequence/cost inputs and conduct shadow-mode planning.

**Stage 2 — physical-loss layer:** add district-metered-area flow/pressure, acoustic events, rainfall, soil and road-work data to identify slow-leak and hydraulic-risk patterns. Validate lead time and field-confirmation rate.

**Stage 3 — shared infrastructure intelligence:** standardised schemas and privacy-preserving cross-utility benchmarks allow state operators and national stakeholders to compare intervention strategies without exposing sensitive raw network data. This remains roadmap, not MVP.

The same decision architecture could later support drains, roads and power assets, but do not dilute the hackathon demo with those domains.

---

## 14. Build plan

### First 24 hours

| Time | Deliverable |
|---|---|
| H0–H4 | Raw-data join, profile, pipe-year table, oldest/random baselines, one complete fold |
| H4–H8 | Walk-forward baseline ladder, leakage tests, `metrics.json` |
| H8–H12 | Champion/challenger model, confidence and risk-pattern logic |
| H12–H16 | Budget selector, action routing and explanation payload |
| H16–H20 | Streamlit worklist and Proof Mode reveal |
| H20–H24 | Robustness run, result freeze, pitch integration and repeated demo rehearsal |

### If 48 hours are available

Add, in order:

1. polished side-by-side map;
2. multi-budget capture curve and bootstrap interval;
3. missingness/OOD stress-test panel;
4. corridor/spatial holdout;
5. scenario calculator; and
6. Malaysian import-schema screen.

Do not add an LLM chat box unless every item above is complete. Templated explanations are safer, faster and more reproducible.

### Four-person split

- **Data/integrity:** extraction, joins, pipe-year panel and leakage tests.
- **ML/evaluation:** baselines, champion/challenger and walk-forward metrics.
- **Decision engine:** consequence inputs, budget selection, confidence-to-action policy and explanations.
- **Product/pitch:** Streamlit, Proof Mode, visual design, slides and demo timing.

### Never-cut items

- credible baseline comparison;
- temporal test;
- budget-constrained worklist;
- evidence card;
- false-selection visibility; and
- validated-versus-scenario separation.

Cut gradient boosting, map polish and scenario sliders before cutting these.

---

## 15. Architecture

```text
Kitchener ArcGIS sources
        │
        ▼
Validated extract + join checks
        │
        ▼
Point-in-time pipe-year features ──► leakage/bias tests
        │
        ▼
Walk-forward baseline + challenger evaluation
        │
        ├──► metrics.json ──► Proof Mode
        │
        ▼
Current risk rank + confidence + risk pattern
        │
        ▼
Consequence assumptions + action costs
        │
        ▼
Budget selector ──► monitor / inspect / renewal-review worklist
        │
        ▼
Streamlit map/table + evidence card + scenario wall
```

Suggested MVP stack: Python, pandas or DuckDB, scikit-learn, GeoPandas only if needed, and Streamlit/Plotly. Prefer a small reproducible stack over infrastructure theatre.

---

## 16. Main risks and mitigations

| Risk | Judge's likely attack | Mitigation |
|---|---|---|
| Imported data | “Why should Kitchener generalise to Malaysia?” | Say it does not yet; demonstrate the method and request a local retrospective pilot |
| Existing prior art | “This has already been built.” | Cite it; implement independently; differentiate on budgeted actions, consequence, confidence, proof mode and Malaysian deployment path |
| NRW mismatch | “Bursts are not the main source of NRW.” | Agree; frame break risk as the renewal wedge and slow-leak sensing as Stage 2 |
| Snapshot leakage | “Today's inventory was used to predict the past.” | Exclude leaking fields, isolate ambiguous histories, run sensitivity analysis and disclose unresolved survivorship |
| Rare positives | “Accuracy is meaningless.” | Use walk-forward capture@budget, precision, PR-AUC and intervals |
| False alarms | “Most selected pipes will not break next year.” | Show workload explicitly; cap it by budget; send uncertain cases to inspection rather than replacement |
| Fake savings | “You did not prevent those historical breaks.” | Claim targeting quality only; put savings behind adjustable scenario assumptions |
| Model loses | “Your AI did not beat a lookup.” | Ship the lookup if it is the robust champion; the product optimises decisions, not algorithm prestige |
| Scope explosion | “National platform is just a slide.” | Ship one excellent decision screen; label every post-pilot feature as roadmap |

### Data fallback

If the Kitchener join cannot pass the four-hour gate, do not fabricate records. First narrow to a manually verified subset and preserve the time-travel evaluation. If a reliable labelled panel still cannot be built, activate a prepared fallback rather than spending the whole event debugging data. The strongest generic fallback from the concept review is top-k transaction-fraud review under a fixed analyst budget, but it is less original and less Malaysia-specific; avoid switching unless necessary.

---

## 17. Judge questions and crisp answers

**“Why are you using Canadian data for a Malaysian problem?”**  
Because no open Malaysian segment-level asset-and-break history was found, and fabricating local proof would be misleading. Kitchener lets us validate the decision method. Malaysian effectiveness must be earned through a utility's retrospective pilot; our adapter and evaluation protocol are ready for that step.

**“Isn't this ordinary predictive maintenance?”**  
The prediction is established. Our differentiator is the decision layer: consequence-aware selection under a real budget, confidence-based action routing, and a same-budget historical test against how assets are commonly prioritised.

**“Does this reduce Malaysia's NRW?”**  
We do not claim that from break records. It targets one measurable infrastructure-renewal event. A local second stage must add DMA flow, pressure and field-confirmed leak data to evaluate physical water-loss reduction.

**“What is the AI?”**  
A point-in-time annual hazard ranker selects the robust champion from an interpretable lookup, regularised logistic model and boosted-tree challenger. The system also identifies descriptive risk patterns and optimises action selection. We choose the model by out-of-time decision performance, not complexity.

**“How do you prove a better decision?”**  
For each past year, we hide outcomes, give every method the same pipe-kilometre budget, build the worklist and reveal the next year's breaks. Capture@budget tells us which method put more real failures inside the actionable set.

**“How do you control false alarms?”**  
The budget caps workload; we report precision and observed non-events at the cutoff; weak evidence lowers spend-confidence; and high-risk/low-confidence segments receive diagnostic inspection rather than automatic renewal.

**“How much money will it save?”**  
The historical data validates targeting, not causal savings. We show a transparent scenario and break-even range using utility-supplied costs and intervention effectiveness. A shadow-mode local pilot is required for a savings claim.

**“Can managers trust the explanation?”**  
Every reason cites observed, time-valid fields; categories are explicitly descriptive; uncertainty and missing data are visible; and a human engineer retains approval.

---

## 18. Claim discipline

### Never say

- “JagaPaip will reduce Malaysian NRW by X%.”
- “We prevent X breaks” based only on retrospective selection.
- “The model is fully leakage-free.”
- “Material X caused this break.”
- “Our model captures 30.1%” unless the team independently reproduces that result.
- “The model works in Malaysia” before local testing.
- “AI decides which pipe to replace.”

### Say instead

- “The selected set contained more recorded next-year breaks at the same budget.”
- “This is a leakage-controlled open-data demonstrator with stated snapshot limitations.”
- “This segment matches a historically higher-risk pattern.”
- “The system recommends inspection or renewal review; an engineer decides.”
- “Savings are scenario-based until an intervention pilot measures them.”
- “Malaysia-ready workflow, Malaysian validation pending.”

---

## Final strategic advice

Spend less time adding models and more time making the **decision proof** undeniable. Judges should leave remembering one interaction:

1. the team fixed the budget;
2. JagaPaip chose the pipes;
3. the team revealed the future; and
4. JagaPaip's worklist beat the baseline—or the team honestly showed where it did not.

That directly answers the brief's core question and makes a credible first step toward a much larger Malaysian infrastructure decision platform.
