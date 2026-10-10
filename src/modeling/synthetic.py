"""Synthetic Contract A generator for development and tests only.

Member 1 owns the real Contract A and its fixture. This generator lets the
modeling lane run offline before that arrives. It simulates breaks year by
year, so history features are genuinely point-in-time. Its outputs are not
results: source_snapshot_date is "SYNTHETIC-FIXTURE", and metrics built from
it are flagged is_synthetic.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .config import TARGET

SNAPSHOT = "SYNTHETIC-FIXTURE"

# Material mix by installation era: (materials, probabilities).
_ERAS = (
    (("CI", "AC", "UNKNOWN"), (0.80, 0.12, 0.08)),  # up to 1954
    (("CI", "AC", "DI", "PVC", "UNKNOWN"), (0.25, 0.30, 0.30, 0.10, 0.05)),  # 1955-1979
    (("DI", "PVC", "PE", "UNKNOWN"), (0.35, 0.55, 0.07, 0.03)),  # 1980 onward
)
_MATERIAL_EFFECT = {"CI": 1.0, "AC": 0.6, "DI": 0.0, "PVC": -0.4, "PE": -0.5, "UNKNOWN": 0.3}
_DIAMETERS = np.array([100, 150, 200, 250, 300, 400, 600], dtype=float)
_DIAMETER_P = np.array([0.15, 0.35, 0.22, 0.08, 0.10, 0.06, 0.04])
_GRID = 10  # 10 x 10 cells of 1 km


def make_synthetic_pipe_year(
    n_segments: int = 600,
    first_year: int = 2008,
    last_year: int = 2023,
    history_start: int = 1995,
    seed: int = 7,
    base_logit: float = -5.5,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ids = np.array([f"SYN-{i:05d}" for i in range(n_segments)])

    install = rng.integers(1925, last_year - 3, size=n_segments)
    era = np.select([install <= 1954, install <= 1979], [0, 1], 2)
    material = np.empty(n_segments, dtype=object)
    for idx, (choices, probs) in enumerate(_ERAS):
        in_era = era == idx
        material[in_era] = rng.choice(choices, size=int(in_era.sum()), p=probs)
    diameter = rng.choice(_DIAMETERS, size=n_segments, p=_DIAMETER_P)
    length = np.clip(rng.lognormal(np.log(110), 0.6, size=n_segments), 5, 1500).round(1)

    x = rng.uniform(0, _GRID * 1000, n_segments)
    y = rng.uniform(0, _GRID * 1000, n_segments)
    cell = (x // 1000).astype(int) * _GRID + (y // 1000).astype(int)
    angle = rng.uniform(0, np.pi, n_segments)
    geometry = np.array(
        [
            f"LINESTRING ({x0:.1f} {y0:.1f}, {x0 + L * np.cos(a):.1f} {y0 + L * np.sin(a):.1f})"
            for x0, y0, L, a in zip(x, y, length, angle)
        ]
    )

    # Hidden drivers the models cannot see directly: local ground conditions
    # (spatial clustering) and per-segment frailty (repeat-break dependence).
    cell_effect = rng.normal(0, 0.4, size=_GRID * _GRID)[cell]
    frailty = rng.normal(0, 0.5, size=n_segments)
    static_logit = (
        base_logit
        + np.array([_MATERIAL_EFFECT[m] for m in material])
        - 0.3 * np.log(diameter / 150)
        + 0.8 * np.log(length / 110)
        + cell_effect
        + frailty
    )

    years = np.arange(history_start, last_year + 1)
    breaks = np.zeros((n_segments, len(years)), dtype=bool)
    prior = np.zeros(n_segments)
    for j, year in enumerate(years):
        logit = static_logit + 0.025 * (year - install) + 0.6 * np.log1p(prior)
        broke = (install <= year) & (rng.random(n_segments) < 1 / (1 + np.exp(-logit)))
        breaks[:, j] = broke
        prior += broke

    # What the source snapshot reports (with realistic gaps).
    reported_install = install.astype(float)
    reported_install[rng.random(n_segments) < 0.03] = np.nan
    reported_diameter = diameter.copy()
    reported_diameter[rng.random(n_segments) < 0.05] = np.nan
    ambiguous = rng.random(n_segments) < 0.01
    flags = np.array(
        [
            json.dumps(
                [
                    flag
                    for flag, present in (
                        ("MISSING_INSTALL_YEAR", np.isnan(ri)),
                        ("MISSING_DIAMETER", np.isnan(rd)),
                        ("UNKNOWN_MATERIAL", m == "UNKNOWN"),
                        ("BREAK_BEFORE_INSTALL", amb),
                    )
                    if present
                ]
            )
            for ri, rd, m, amb in zip(reported_install, reported_diameter, material, ambiguous)
        ]
    )

    cumulative = np.cumsum(breaks, axis=1)
    cell_cumulative = np.zeros((_GRID * _GRID, len(years)))
    np.add.at(cell_cumulative, cell, cumulative)

    frames = []
    for j in range(first_year - history_start, len(years)):
        year = int(years[j])
        rows = np.flatnonzero(install <= year)
        prior_count = cumulative[rows, j - 1]
        # Index of the most recent break strictly before this year.
        last_idx = j - 1 - np.argmax(breaks[rows, :j][:, ::-1], axis=1)
        since_last = np.where(prior_count > 0, year - (years[last_idx] + 0.5), np.nan)
        frames.append(
            pd.DataFrame(
                {
                    "segment_id": ids[rows],
                    "score_year": np.full(len(rows), year, dtype="int64"),
                    "install_year": pd.array(reported_install[rows], dtype="Int64"),
                    "age_years": year - reported_install[rows],
                    "material": material[rows].astype(str),
                    "diameter_mm": reported_diameter[rows],
                    "length_m": length[rows],
                    "prior_break_count": prior_count.astype("int64"),
                    "years_since_last_break": since_last,
                    "nearby_prior_breaks": (cell_cumulative[cell[rows], j - 1] - prior_count).astype("int64"),
                    "is_ambiguous_history": ambiguous[rows],
                    "data_quality_flags": flags[rows],
                    "geometry_wkt": geometry[rows],
                    TARGET: breaks[rows, j].astype("int64"),
                    "source_snapshot_date": SNAPSHOT,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)
