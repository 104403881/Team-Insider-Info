"""Synthetic network used only when team artifacts are not in the folder.

Breaks are simulated from age and material so the screens have something to
show. That is a property of this generator, not a utility result.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from jagapaip.schema import DEMO_DECISION_YEAR

DEMO_PIPE_COUNT = 64
DEMO_SEED = 42

_MATERIALS = ["Cast Iron", "Asbestos Cement", "Ductile Iron", "PVC", "HDPE"]
_MATERIAL_P = [0.28, 0.18, 0.22, 0.22, 0.10]
_ZONES = ["North feeder", "Central grid", "South feeder", "East main", "West main"]
_DIAMETERS = [100, 150, 200, 300]
_BREAK_MATERIAL = {
    "Cast Iron": 0.045,
    "Asbestos Cement": 0.032,
    "Ductile Iron": 0.012,
    "PVC": 0.004,
    "HDPE": 0.003,
}


def build_demo_tables(seed: int = DEMO_SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return deterministic pipe attributes and a year-level break ledger."""
    rng = np.random.default_rng(seed)
    install_year = rng.integers(1958, 2019, size=DEMO_PIPE_COUNT)
    material = rng.choice(_MATERIALS, size=DEMO_PIPE_COUNT, p=_MATERIAL_P)
    zone = rng.choice(_ZONES, size=DEMO_PIPE_COUNT)
    diameter_mm = rng.choice(_DIAMETERS, size=DEMO_PIPE_COUNT)
    length_m = rng.uniform(45, 260, size=DEMO_PIPE_COUNT).round(1)

    pipes = pd.DataFrame(
        {
            "pipe_id": [f"JP-{1001 + i}" for i in range(DEMO_PIPE_COUNT)],
            "zone": zone,
            "material": material,
            "install_year": install_year.astype(int),
            "length_m": length_m.astype(float),
            "diameter_mm": diameter_mm.astype(int),
        }
    )

    events: list[tuple[str, int, int]] = []
    for pipe in pipes.itertuples(index=False):
        first_year = max(int(pipe.install_year), 1998)
        for year in range(first_year, DEMO_DECISION_YEAR + 1):
            age = year - int(pipe.install_year)
            probability = min(0.40, 0.008 + _BREAK_MATERIAL[pipe.material] + 0.0011 * age)
            if rng.random() < probability:
                events.append((pipe.pipe_id, year, 1))

    breaks = pd.DataFrame(events, columns=["pipe_id", "break_year", "break_count"])
    if breaks.empty:
        breaks = pd.DataFrame(columns=["pipe_id", "break_year", "break_count"])
    return pipes, breaks
