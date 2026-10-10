"""The synthetic Contract A must behave like a real snapshot, not a toy."""

import json

import pytest

from src.modeling.synthetic import DEFAULT_SEGMENTS, make_synthetic_pipe_year


@pytest.fixture(scope="module")
def default_fixture():
    return make_synthetic_pipe_year()  # the settings used for contracts/fixtures


def test_pipes_that_keep_breaking_get_replaced(default_fixture):
    # Without replacement a few pipes broke almost every year (25+ prior breaks)
    # and the same segments topped every year's ranking.
    assert default_fixture["prior_break_count"].max() <= 12


def test_replacements_create_new_asset_ids(default_fixture):
    original_ids = {f"SYN-{i:05d}" for i in range(DEFAULT_SEGMENTS)}
    assert set(default_fixture["segment_id"]) - original_ids


def test_reused_ids_produce_flagged_ambiguous_histories(default_fixture):
    ambiguous = default_fixture[default_fixture["is_ambiguous_history"]]
    assert len(ambiguous) > 0
    flags = ambiguous["data_quality_flags"].map(json.loads)
    assert flags.map(lambda f: "BREAK_BEFORE_INSTALL" in f).all()
    unflagged = default_fixture[~default_fixture["is_ambiguous_history"]]["data_quality_flags"].map(json.loads)
    assert not unflagged.map(lambda f: "BREAK_BEFORE_INSTALL" in f).any()


def test_generator_is_deterministic():
    first = make_synthetic_pipe_year(n_segments=100, seed=3)
    second = make_synthetic_pipe_year(n_segments=100, seed=3)
    assert first.equals(second)
