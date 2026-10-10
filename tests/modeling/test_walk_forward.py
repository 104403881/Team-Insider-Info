from pathlib import Path

import pytest

from src.modeling.splits import default_test_years, split_frame, walk_forward_folds

MODELING_SRC = Path(__file__).resolve().parents[2] / "src" / "modeling"


def test_each_fold_trains_only_on_earlier_years():
    folds = walk_forward_folds(range(2010, 2024), [2021, 2022, 2023])
    assert [f.test_year for f in folds] == [2021, 2022, 2023]
    for fold in folds:
        assert max(fold.train_years) == fold.test_year - 1
        assert min(fold.train_years) == 2010
        assert fold.test_year not in fold.train_years


def test_training_window_expands():
    early, late = walk_forward_folds(range(2010, 2024), [2021, 2022])
    assert set(early.train_years) < set(late.train_years)


def test_rejects_test_year_without_rows():
    with pytest.raises(ValueError, match="no rows"):
        walk_forward_folds(range(2010, 2020), [2021])


def test_rejects_test_year_with_too_little_history():
    with pytest.raises(ValueError, match="prior years"):
        walk_forward_folds(range(2010, 2024), [2011], min_train_years=3)


def test_split_frame_has_no_overlap(pipe_year):
    fold = walk_forward_folds(pipe_year["score_year"].unique(), [2022])[0]
    train, test = split_frame(pipe_year, fold)
    assert train["score_year"].max() < 2022
    assert set(test["score_year"]) == {2022}
    assert len(train) + len(test) == (pipe_year["score_year"] <= 2022).sum()


def test_default_test_years_are_latest_with_enough_history():
    assert default_test_years(range(2008, 2024), n=3, min_train_years=3) == [2021, 2022, 2023]
    assert default_test_years(range(2008, 2012), n=3, min_train_years=3) == [2011]


def test_no_random_row_split_in_result_code():
    """Definition of done: no random row split exists in result-generating code."""
    banned = ("train_test_split", "KFold", "ShuffleSplit", "cross_val_score", "cross_val_predict")
    for path in MODELING_SRC.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path.name} uses {token}"
