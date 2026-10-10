"""Ranking methods: the baseline ladder plus the champion candidates.

Every ranker is fitted on training years only and then scores one test year.
``score`` never receives the test-year target column. Larger scores mean
higher risk.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .config import SEED, TARGET
from .features import cohort_label, material_label, numeric


class Ranker:
    name = "base"

    def __init__(self, seed: int = SEED):
        self.seed = seed

    def fit(self, train: pd.DataFrame) -> "Ranker":
        return self

    def score(self, test: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError


def _unit_hash(text: str) -> float:
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2**64


class RandomRanker(Ranker):
    """Seeded random order. Each draw depends only on (seed, year, segment_id),
    so it does not change with row order or with which other segments exist."""

    name = "random"

    def score(self, test):
        return np.array(
            [
                _unit_hash(f"{self.seed}|{year}|{segment}")
                for year, segment in zip(test["score_year"], test["segment_id"])
            ]
        )


class OldestFirstRanker(Ranker):
    """Oldest pipe first; unknown ages rank last."""

    name = "oldest"

    def score(self, test):
        return numeric(test["age_years"]).fillna(-1.0).to_numpy()


class PriorBreaksRanker(Ranker):
    """Most recorded breaks before the score date first."""

    name = "prior_breaks"

    def score(self, test):
        return numeric(test["prior_break_count"]).fillna(0.0).to_numpy()


class SmoothedLookupRanker(Ranker):
    """Smoothed break rate for prior-break bucket x material x install decade.

    Each level shrinks toward its parent, rate = (events + k * parent) / (n + k),
    along global -> prior-break bucket -> + material -> + decade. The strongest
    signal sits at the top, so sparse cells shrink toward a sensible rate.
    Cells unseen in training fall back to the deepest level that was seen.
    """

    name = "lookup"
    LEVELS = (
        ("pb_bucket",),
        ("pb_bucket", "material"),
        ("pb_bucket", "material", "cohort"),
    )

    def __init__(self, seed: int = SEED, prior_strength: float = 100.0):
        super().__init__(seed)
        self.prior_strength = prior_strength

    @staticmethod
    def _cells(df):
        prior = numeric(df["prior_break_count"]).fillna(0.0)
        return pd.DataFrame(
            {
                "pb_bucket": np.select([prior <= 0, prior == 1], ["0", "1"], "2+"),
                "material": material_label(df["material"]).to_numpy(),
                "cohort": cohort_label(df["install_year"]).to_numpy(),
            }
        )

    @staticmethod
    def _lookup(cells, level, table):
        keys = list(level)
        return cells[keys].merge(table[keys + ["rate"]], on=keys, how="left")["rate"]

    def fit(self, train):
        cells = self._cells(train)
        events = train[TARGET].to_numpy(dtype=float)
        self.global_rate_ = float(events.mean())
        parent = np.full(len(cells), self.global_rate_)
        self.tables_ = []
        for level in self.LEVELS:
            frame = cells[list(level)].assign(events=events, parent=parent)
            table = frame.groupby(list(level), as_index=False).agg(
                n=("events", "size"), events=("events", "sum"), parent=("parent", "first")
            )
            table["rate"] = (table["events"] + self.prior_strength * table["parent"]) / (
                table["n"] + self.prior_strength
            )
            self.tables_.append(table)
            parent = self._lookup(cells, level, table).to_numpy()
        return self

    def score(self, test):
        cells = self._cells(test)
        rate = pd.Series(self.global_rate_, index=cells.index)
        for level, table in zip(self.LEVELS, self.tables_):
            rate = self._lookup(cells, level, table).fillna(rate)
        return rate.to_numpy(dtype=float)


class LogisticHazardRanker(Ranker):
    """L2-regularised logistic model on pipe-years (a discrete-time hazard).

    All preprocessing lives inside the pipeline, so imputation, scaling and
    category encodings are fitted on training years only.
    """

    name = "logistic"
    NUMERIC = [
        "age_years",
        "log_length",
        "log_diameter",
        "log_prior_breaks",
        "break_recency",
        "log_nearby_breaks",
    ]
    CATEGORICAL = ["material", "cohort"]

    def __init__(self, seed: int = SEED, C: float = 1.0):
        super().__init__(seed)
        self.C = C

    @staticmethod
    def features(df):
        diameter = numeric(df["diameter_mm"])
        since_last = numeric(df["years_since_last_break"])
        if "nearby_prior_breaks" in df:
            nearby = numeric(df["nearby_prior_breaks"])
        else:
            nearby = pd.Series(np.nan, index=df.index)
        return pd.DataFrame(
            {
                "age_years": numeric(df["age_years"]),
                "log_length": np.log(numeric(df["length_m"])),
                "log_diameter": np.log(diameter.where(diameter > 0)),
                "log_prior_breaks": np.log1p(numeric(df["prior_break_count"])),
                # 0 for a segment that has never broken, near 1 for a very recent break.
                "break_recency": (1.0 / (1.0 + since_last)).fillna(0.0),
                "log_nearby_breaks": np.log1p(nearby),
                "material": material_label(df["material"]).astype(object),
                "cohort": cohort_label(df["install_year"]).astype(object),
            },
            index=df.index,
        )

    def fit(self, train):
        y = train[TARGET].to_numpy(dtype=int)
        self.constant_ = None
        if y.min() == y.max():
            # Degenerate fold with a single class: nothing to learn from.
            self.constant_ = float(y[0])
            return self
        preprocess = ColumnTransformer(
            [
                (
                    "num",
                    make_pipeline(
                        SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
                        StandardScaler(),
                    ),
                    self.NUMERIC,
                ),
                ("cat", OneHotEncoder(handle_unknown="ignore"), self.CATEGORICAL),
            ]
        )
        self.pipeline_ = make_pipeline(preprocess, LogisticRegression(C=self.C, max_iter=2000))
        self.pipeline_.fit(self.features(train), y)
        return self

    def score(self, test):
        if self.constant_ is not None:
            return np.full(len(test), self.constant_)
        return self.pipeline_.predict_proba(self.features(test))[:, 1]


RANKERS: dict[str, type[Ranker]] = {
    cls.name: cls
    for cls in (
        RandomRanker,
        OldestFirstRanker,
        PriorBreaksRanker,
        SmoothedLookupRanker,
        LogisticHazardRanker,
    )
}
