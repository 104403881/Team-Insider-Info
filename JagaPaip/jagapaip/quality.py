"""Data-quality checks and provenance labels for the loaded dataset."""

from __future__ import annotations

import pandas as pd

PASS = "Pass"
WARN = "Warning"
INFO = "Info"
MISSING = "Missing"

LONG_SEGMENT_M = 5000


def _count(mask: pd.Series) -> int:
    return int(mask.fillna(False).sum())


def run_checks(dataset: dict) -> list[dict]:
    """Checks on the loaded tables. Each row reports a count, never a fix."""
    pipes = dataset["pipes"]
    breaks = dataset["breaks"]
    predictions = dataset["predictions"]
    year = int(dataset["meta"]["decision_year"])
    rows: list[dict] = []

    def add(check: str, status: str, count: int | None, detail: str) -> None:
        rows.append({"Check": check, "Status": status, "Count": count, "Detail": detail})

    ids = pipes["pipe_id"].astype(str)
    dupes = int(ids.duplicated().sum())
    add("Unique pipe IDs", PASS if dupes == 0 else WARN, dupes, "Duplicate IDs in the attribute table." if dupes else "Every pipe ID appears once.")

    length = pd.to_numeric(pipes["length_m"], errors="coerce")
    bad_length = _count(length.isna() | (length <= 0))
    add("Usable length", PASS if bad_length == 0 else WARN, bad_length, "Segments without a positive length are not eligible for the budget.")
    long = _count(length > LONG_SEGMENT_M)
    add(f"Segments over {LONG_SEGMENT_M:,} m", PASS if long == 0 else WARN, long, "Unusually long segments may be units or digitising errors.")

    install = pd.to_numeric(pipes["install_year"], errors="coerce")
    no_install = _count(install.isna())
    add("Install year present", PASS if no_install == 0 else WARN, no_install, "Missing install year removes the segment from age-based ranking and oldest-first.")
    future_install = _count(install > year)
    add("Installed after decision year", INFO, future_install, f"Not in service at {year}, so not ranked.")

    material = pipes["material"].astype(str).str.strip().str.lower()
    unknown = _count(pipes["material"].isna() | material.isin(["", "unknown", "nan", "none"]))
    add("Material recorded", PASS if unknown == 0 else WARN, unknown, "Unknown material uses a neutral heuristic weight.")

    if "diameter_mm" in pipes.columns:
        no_diam = _count(pd.to_numeric(pipes["diameter_mm"], errors="coerce").isna())
        add("Diameter recorded", PASS if no_diam == 0 else INFO, no_diam, "Diameter is shown as evidence. It is not a ranking input.")

    if breaks is None:
        add("Dated break ledger", MISSING, None, "No year-level breaks. Proof Mode cannot hold out an outcome window.")
    else:
        years = pd.to_numeric(breaks["break_year"], errors="coerce")
        span = f"{int(years.min())} to {int(years.max())}" if years.notna().any() else "undated"
        add("Dated break ledger", PASS, int(len(breaks)), f"Break records span {span}.")
        known_ids = set(ids)
        orphan = _count(~breaks["pipe_id"].astype(str).isin(known_ids))
        add("Breaks on known pipes", PASS if orphan == 0 else WARN, orphan, "Break rows whose pipe ID is not in the attribute table are ignored.")
        merged = breaks.assign(pipe_id=breaks["pipe_id"].astype(str)).merge(
            pipes.assign(pipe_id=ids)[["pipe_id", "install_year"]], on="pipe_id", how="inner"
        )
        early = _count(pd.to_numeric(merged["break_year"], errors="coerce") < pd.to_numeric(merged["install_year"], errors="coerce"))
        add("Breaks after installation", PASS if early == 0 else WARN, early, "Breaks dated before the install year are excluded from history.")

    if predictions is None:
        add("Model predictions", MISSING, None, "No fold_predictions file. Scores are the screening heuristic.")
    else:
        use = predictions
        if "year" in predictions.columns and predictions["year"].notna().any():
            use = predictions.loc[predictions["year"] == year]
        in_service = set(ids[install.notna() & (install <= year)])
        covered = len(in_service.intersection(set(use["pipe_id"].astype(str))))
        share = 0 if not in_service else covered / len(in_service)
        add(
            f"Prediction coverage, {year}",
            PASS if share >= 0.999 else WARN,
            covered,
            f"{share:.0%} of in-service segments have a supplied score. The rest use the heuristic.",
        )
        scores = pd.to_numeric(predictions["predicted_risk"], errors="coerce")
        outside = _count((scores < 0) | (scores > 1))
        add("Scores within 0 to 1", PASS if outside == 0 else WARN, outside, "Action bands assume a 0 to 1 scale.")
    return rows


def provenance(dataset: dict, score_source: str) -> list[dict]:
    """Label every displayed quantity by where it comes from."""
    meta = dataset["meta"]
    demo = meta["mode"] == "demo"
    observed = (
        "City of Kitchener open data — method demonstrator, not Malaysian validation"
        if meta.get("demonstrator")
        else "Observed data from file (provenance not verified by JagaPaip)"
    )
    rows = [
        {
            "Element": "Pipe attributes (material, install year, length)",
            "Classification": "Synthetic demonstration data" if demo else observed,
            "Source": "Built-in demo generator" if demo else meta["files"].get("pipe_year", ""),
        },
        {
            "Element": "Break history",
            "Classification": (
                "Synthetic demonstration data"
                if demo
                else (observed if dataset["breaks"] is not None else "Missing")
            ),
            "Source": "Built-in demo generator" if demo else (meta["files"].get("breaks_clean") or meta["files"].get("pipe_year") or "—"),
        },
        {
            "Element": "Risk scores",
            "Classification": "Model predictions (supplied)" if score_source == "Supplied predictions" else (
                "Model predictions with screening-heuristic fill" if "heuristic fill" in score_source else "Screening heuristic (not a trained model)"
            ),
            "Source": meta["files"].get("fold_predictions", "") or "jagapaip/ranking.py heuristic",
        },
        {
            "Element": "Evaluation metrics",
            "Classification": "Measured result, as reported in metrics.json" if dataset["metrics"] is not None else "Missing — not yet evaluated",
            "Source": meta["files"].get("metrics", "") or "—",
        },
        {
            "Element": "Proof Mode comparison",
            "Classification": (
                "Simulated on synthetic data — not a validation"
                if demo
                else ("Computed from loaded ledger — not independently validated" if dataset["breaks"] is not None else "Unavailable")
            ),
            "Source": "jagapaip/backtest.py",
        },
        {
            "Element": "Worklist review marks",
            "Classification": "Session-only operator notes — not measured outcomes",
            "Source": "Browser session on this dashboard",
        },
    ]
    return rows


def field_validation_needs() -> list[dict]:
    """What a utility would still need before claiming effectiveness."""
    return [
        {
            "Requirement": "Local pipe inventory",
            "Why it is required": "Material, install year, length, diameter, and location from the utility that would use the plan.",
        },
        {
            "Requirement": "Dated break or leak records",
            "Why it is required": "A hold-out window after each decision year, so ranking can be scored against events that were not used to rank.",
        },
        {
            "Requirement": "Recorded interventions and costs",
            "Why it is required": "Which segments were actually inspected or renewed, and what they cost, so a length budget can be replaced by a real budget.",
        },
        {
            "Requirement": "Post-decision outcomes on treated and untreated pipes",
            "Why it is required": "Without follow-up records, capture rates stay a historical bookkeeping check, not evidence that intervention worked.",
        },
        {
            "Requirement": "A fresh evaluation design on that network",
            "Why it is required": "Rolling-origin or held-out years on the local ledger. City of Kitchener or demo numbers do not transfer.",
        },
    ]
