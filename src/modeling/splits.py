"""Year-based walk-forward splits. There is deliberately no random row split."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from .config import MIN_TRAIN_YEARS, N_TEST_YEARS


@dataclass(frozen=True)
class Fold:
    test_year: int
    train_years: tuple[int, ...]


def walk_forward_folds(
    available_years: Iterable[int],
    test_years: Iterable[int],
    min_train_years: int = MIN_TRAIN_YEARS,
) -> list[Fold]:
    """Expanding-window folds: test year Y trains on every available year < Y.

    A row for score_year t carries the outcome during t, which is fully known
    before 1 January t+1. Training on all years < Y therefore uses only
    information available when year Y is scored.
    """
    years = sorted({int(y) for y in available_years})
    folds = []
    for test_year in sorted({int(y) for y in test_years}):
        if test_year not in years:
            raise ValueError(f"test year {test_year} has no rows in the panel")
        train_years = tuple(y for y in years if y < test_year)
        if len(train_years) < min_train_years:
            raise ValueError(
                f"test year {test_year} has {len(train_years)} prior years; "
                f"need at least {min_train_years}"
            )
        folds.append(Fold(test_year, train_years))
    return folds


def default_test_years(
    available_years: Iterable[int],
    n: int = N_TEST_YEARS,
    min_train_years: int = MIN_TRAIN_YEARS,
) -> list[int]:
    """The latest ``n`` years that still have ``min_train_years`` of history."""
    years = sorted({int(y) for y in available_years})
    eligible = years[min_train_years:]
    if not eligible:
        raise ValueError(f"need more than {min_train_years} score years, found {years}")
    return eligible[-n:]


def split_frame(
    df: pd.DataFrame, fold: Fold, year_col: str = "score_year"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = df[df[year_col].isin(fold.train_years)]
    test = df[df[year_col] == fold.test_year]
    if len(train) and train[year_col].max() >= fold.test_year:
        raise AssertionError("training rows overlap the test year")
    return train, test
