"""Adapter: Member 1's data package -> Contract A 1.0.

Member 1's ``data/data/pipe_year.parquet`` uses its own field names
(see data/data_dictionary.md). This adapter maps them onto the frozen
Contract A so the modeling lane runs on the real data unchanged.

Mapping decisions:

* year -> score_year, installation_year -> install_year,
  pipe_size_mm -> diameter_mm, ambiguous_asset_history -> is_ambiguous_history,
  and segment_id becomes a string.
* data_quality_flags is built from material_unknown (UNKNOWN_MATERIAL),
  pipe_size_missing (MISSING_DIAMETER) and ambiguous_asset_history
  (BREAK_BEFORE_INSTALL). installation_date_jan1 is deliberately left out:
  it marks year-only date precision on ~43% of rows, and flagging it would
  downgrade half the network to MEDIUM confidence over +/-1 year of age.
* source_snapshot_date comes from manifest.json snapshot_date.
* Score years before BURN_IN_FIRST_SCORE_YEAR are dropped. The break log
  starts in 1997, so earlier years have almost no recorded history; Member 1's
  report recommends treating them as burn-in. Their breaks still count in
  later years' prior_break_count, which Member 1 computed from the full log.
* nearby_prior_breaks and geometry_wkt are optional and not provided;
  Member 4 joins geometry from data/data/pipes.geojson by segment_id.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import TARGET
from .features import numeric

MEMBER1_PIPE_YEAR = Path("data") / "pipe_year.parquet"  # relative to the package root
MEMBER1_MANIFEST = Path("manifest.json")
BURN_IN_FIRST_SCORE_YEAR = 2000

_FLAG_COLUMNS = (
    ("material_unknown", "UNKNOWN_MATERIAL"),
    ("pipe_size_missing", "MISSING_DIAMETER"),
    ("ambiguous_asset_history", "BREAK_BEFORE_INSTALL"),
)


def _quality_flags(df: pd.DataFrame) -> np.ndarray:
    """JSON-array text per row, built from Member 1's boolean QA columns."""
    present = [(df[col].fillna(False).astype(bool).to_numpy(), name) for col, name in _FLAG_COLUMNS if col in df]
    code = np.zeros(len(df), dtype=int)
    for bit, (mask, _) in enumerate(present):
        code |= mask.astype(int) << bit
    lookup = {
        k: json.dumps([name for bit, (_, name) in enumerate(present) if k >> bit & 1])
        for k in range(1 << len(present))
    }
    return pd.Series(code).map(lookup).to_numpy()


def adapt_member1_pipe_year(
    df: pd.DataFrame, snapshot_date: str, first_score_year: int = BURN_IN_FIRST_SCORE_YEAR
) -> pd.DataFrame:
    """Map Member 1's pipe_year columns onto Contract A."""
    if "eligible_inventory" in df:
        df = df[df["eligible_inventory"].astype(bool)]
    df = df[df["year"] >= first_score_year]
    return pd.DataFrame(
        {
            "segment_id": df["segment_id"].astype(str).to_numpy(),
            "score_year": df["year"].astype("int64").to_numpy(),
            "install_year": df["installation_year"].astype("Int64").to_numpy(),
            "age_years": numeric(df["age_years"]).to_numpy(),
            "material": df["material"].fillna("UNKNOWN").astype(str).to_numpy(),
            "diameter_mm": numeric(df["pipe_size_mm"]).to_numpy(),
            "length_m": numeric(df["length_m"]).to_numpy(),
            "prior_break_count": df["prior_break_count"].astype("int64").to_numpy(),
            "years_since_last_break": numeric(df["years_since_last_break"]).to_numpy(),
            "is_ambiguous_history": df["ambiguous_asset_history"].astype(bool).to_numpy(),
            "data_quality_flags": _quality_flags(df),
            TARGET: df["target_next_year_break"].astype("int64").to_numpy(),
            "source_snapshot_date": snapshot_date,
        }
    )


def load_member1_package(root: Path, first_score_year: int = BURN_IN_FIRST_SCORE_YEAR) -> pd.DataFrame:
    """Read Member 1's package (e.g. ``data/``) and return a Contract A frame."""
    root = Path(root)
    manifest = json.loads((root / MEMBER1_MANIFEST).read_text(encoding="utf-8"))
    pipe_year = pd.read_parquet(root / MEMBER1_PIPE_YEAR)
    return adapt_member1_pipe_year(pipe_year, manifest["snapshot_date"], first_score_year)
