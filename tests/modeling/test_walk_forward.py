import datetime
from pathlib import Path

import pandas as pd
import pytest

from src.modeling.evaluate import run_evaluation
from src.modeling.run_evaluation import main
from src.modeling.splits import default_test_years, last_complete_year, split_frame, walk_forward_folds

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


@pytest.mark.parametrize(
    "snapshots, expected",
    [
        (["2026-10-10"], 2025),
        (["2026-01-01"], 2025),
        (["2026-10-10", "2025-06-30"], 2024),  # the earliest snapshot wins
        ([datetime.date(2024, 3, 1)], 2023),
        (["Sat, 10 Oct 2026 00:00:00 GMT"], 2025),
        (["SYNTHETIC-FIXTURE"], None),
        (["2026-10-10", "not a date"], None),
    ],
)
def test_last_complete_year(snapshots, expected):
    assert last_complete_year(snapshots) == expected


def test_incomplete_years_are_dropped_and_never_tested(pipe_year):
    # A mid-2023 snapshot: 2023 outcomes are partial, so 2022 is the last usable year.
    result = run_evaluation(pipe_year.assign(source_snapshot_date="2023-06-30"), run_sensitivity=False)
    assert result.metrics["test_years"] == [2020, 2021, 2022]
    assert result.metrics["inputs"]["outcomes_complete_through"] == 2022
    assert result.metrics["inputs"]["incomplete_score_years_excluded"] == [2023]


def test_rows_from_incomplete_years_do_not_change_results(pipe_year):
    complete_only = pipe_year[pipe_year["score_year"] <= 2022].assign(source_snapshot_date="2023-06-30")
    with_partial_year = pipe_year.assign(source_snapshot_date="2023-06-30")
    pd.testing.assert_frame_equal(
        run_evaluation(complete_only, run_sensitivity=False).contract_b,
        run_evaluation(with_partial_year, run_sensitivity=False).contract_b,
    )


def test_requesting_an_incomplete_test_year_fails(pipe_year):
    with pytest.raises(ValueError, match=r"test years \[2023\] are incomplete"):
        run_evaluation(
            pipe_year.assign(source_snapshot_date="2023-06-30"),
            test_years=[2021, 2022, 2023],
            run_sensitivity=False,
        )


def test_real_data_needs_a_date_snapshot(pipe_year):
    with pytest.raises(ValueError, match="source_snapshot_date must be a date"):
        run_evaluation(pipe_year.assign(source_snapshot_date="unknown"), run_sensitivity=False)


def test_cli_reports_bad_test_year_without_traceback(tmp_path, capsys):
    code = main(
        [
            "--synthetic",
            "--synthetic-segments", "100",
            "--test-years", "2030",
            "--predictions-out", str(tmp_path / "p.parquet"),
            "--metrics-out", str(tmp_path / "m.json"),
        ]
    )
    assert code == 2
    assert "incomplete" in capsys.readouterr().err
    assert not (tmp_path / "p.parquet").exists()


def test_no_random_row_split_in_result_code():
    """Definition of done: no random row split exists in result-generating code."""
    banned = ("train_test_split", "KFold", "ShuffleSplit", "cross_val_score", "cross_val_predict")
    for path in MODELING_SRC.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path.name} uses {token}"
