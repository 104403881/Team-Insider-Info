"""Member 1's definition of done: Member 2's contract validator accepts the file."""

import pandas as pd
import pytest

from src.modeling.contracts import validate_pipe_year


def test_synthetic_contract_a_passes(pipe_year):
    assert validate_pipe_year(pipe_year).errors == []


@pytest.mark.parametrize(
    "break_it, message",
    [
        (lambda df: df.assign(condition_score=1.0), "forbidden"),
        (lambda df: pd.concat([df, df.head(1)]), "duplicate"),
        (lambda df: df.assign(target_next_year_break=2), "values outside"),
        (lambda df: df.assign(length_m=-1.0), "must be >"),
        (lambda df: df.assign(prior_break_count=-1), "below minimum"),
        (lambda df: df.drop(columns=["material"]), "missing required column"),
        (lambda df: df.assign(age_years=-3.0, is_ambiguous_history=False), "negative age"),
        (lambda df: df.assign(age_years=df["age_years"] + 1), "score_year - install_year"),
        (lambda df: df.assign(data_quality_flags="MISSING_DIAMETER"), "not JSON arrays"),
    ],
)
def test_contract_a_violations_are_caught(pipe_year, break_it, message):
    errors = validate_pipe_year(break_it(pipe_year)).errors
    assert any(message in e for e in errors), errors
