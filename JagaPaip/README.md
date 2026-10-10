# JagaPaip

JagaPaip helps a water-utility asset manager choose which pipe segments to monitor, inspect, or put forward for renewal review when the annual programme cannot cover the whole network.

Tagline: **Know which pipe first.**

The app runs locally in Google Chrome. It does not need an API key or an internet connection after the Python packages are installed.

## What you are looking at

If `data/pipe_year.parquet` is not in the folder, the screens use a small synthetic network. That state is labelled **DEMO DATA — NOT REAL UTILITY DATA**. It is there so the interface can be demonstrated. It is not a utility measurement and it is not a validated result.

City of Kitchener data, if the team connects it later, is a method demonstrator only. It does not establish effectiveness for Malaysian utilities. A Malaysian pilot needs local pipe inventory, break history, and a defined decision year.

## Where team files go

Inside the team repository the app finds the handoffs by itself; nothing needs copying:

| File | Where it is read from | Role |
| --- | --- | --- |
| `pipe_year.parquet`, `features.parquet`, `breaks_clean.parquet` ... | `data/data/` (Member 1) | Pipe attributes, point-in-time features, dated breaks |
| `manifest.json` | `data/` (Member 1) | Snapshot date and source provenance |
| `fold_predictions.parquet` | `artifacts/` (Member 2, Contract B) | The measured champion's out-of-sample risk percentiles, plus the baselines |
| `metrics.json` | `artifacts/` (Member 2) | Every Proof Mode number. Shown as written, never recomputed |
| `ranked_worklists.parquet` | `artifacts/` (Member 3, Contract C) | Recommended actions for the worklist |

A file dropped into this app's `data` folder takes precedence, which is handy for testing. Keep that folder empty for the demo.

**Contract mode.** When Contract B and `metrics.json` are present, the worklist ranks by the champion's `risk_percentile` (ties by pipe ID), recommended actions come from Contract C (shown as *Awaiting decision engine* until it exists), and Proof Mode shows the measured walk-forward comparison: both plans come from Contract B, every count and rate is copied from `metrics.json`, and a mismatch is flagged *do not present*. Without those files the app falls back to the screening heuristic and labels it.

Every budget walks the ranked list and **stops at the first segment that does not fit**, the team's frozen rule, so app plans, `metrics.json` and the decision engine agree.

## Pages and evaluation metrics

- **Overview** includes a five-step guided demo for judges.
- **Risk Worklist** filters by pipe ID, band, action, plan status, material, zone, and age; sorts for display only; explains each rank; and exports the current view or the funded plan as CSV.
- **Proof Mode** (heuristic fallback, without Contract B) builds both plans from facts at the chosen year, then reads outcomes only after **Reveal Actual Outcomes**. It reports:
  - **Capture rate** = window breaks on selected segments ÷ all window breaks on the eligible population.
  - **Capture@5%** = capture rate with a budget of 5% of eligible network length.
  - **Ratio** = JagaPaip ÷ oldest-first capture at the same budget.
  - The eligible population is segments in service at the decision year with a positive length. On demo data these numbers are a mechanics check, not a validated result.
- **Evaluation & Data Quality** labels each quantity (synthetic, observed, heuristic, model prediction, measured, or missing) and runs data-quality checks.

Code layout: `ranking.py` (score and budget), `proof.py` (decision-year snapshot), `backtest.py` (Proof Mode metrics), `worklist.py` (filters, sorting, reasons, export), `quality.py` (checks and provenance), `views.py` and `workflows.py` (pages).

## Windows setup in Cursor

Open the Cursor terminal (Terminal → New Terminal). It should start in this folder. Then run these commands one at a time.

Create the environment and install packages:

```powershell
cd <path to the repository>\JagaPaip
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Start the app:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Open it in Google Chrome

When the terminal says the app is ready, open:

http://localhost:8501

Leave the terminal running while you use the app.

## Stop and start again

1. Click the terminal panel.
2. Press `Ctrl+C`.
3. Wait until the prompt returns.
4. Start the app again with:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

If port 8501 is already in use, either stop the older terminal with `Ctrl+C` or start on another port:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8502
```

Then open http://localhost:8502 instead.

## If a command fails

- `python` is not recognized: install Python 3.12 from [python.org](https://www.python.org/downloads/windows/) and tick **Add python.exe to PATH**. Close and reopen Cursor.
- Package install fails: check that you are in the repository's `JagaPaip` folder and run the `pip install` command again.
- The page does not load: confirm the terminal still shows Streamlit running, then try http://127.0.0.1:8501 in Chrome.
