import numpy as np
import pandas as pd
import pytest

from src.modeling.budget import capture_at_budget, evaluate_budget, precision_at_budget


def ranking(lengths, breaks, scores=None, ids=None):
    n = len(lengths)
    return pd.DataFrame(
        {
            "segment_id": ids if ids is not None else [f"S{i}" for i in range(n)],
            "risk_percentile": scores if scores is not None else np.linspace(1, 0.1, n),
            "length_m": lengths,
            "actual_break": breaks,
        }
    )


def test_hand_computed_example():
    # 1,000 m network; a 30% budget is 300 m = the three highest-ranked 100 m segments.
    group = ranking([100, 100, 100, 100, 600], [1, 0, 1, 0, 1])
    outcome = evaluate_budget(group, 0.30)
    assert outcome.budget_length_m == pytest.approx(300)
    assert outcome.selected_segments == 3
    assert outcome.selected_length_m == pytest.approx(300)
    assert outcome.breaks_captured == 2
    assert outcome.total_breaks == 3
    assert outcome.capture == pytest.approx(2 / 3)
    assert outcome.precision == pytest.approx(2 / 3)
    assert outcome.observed_non_events == 1
    assert capture_at_budget(group, 0.30) == pytest.approx(2 / 3)
    assert precision_at_budget(group, 0.30) == pytest.approx(2 / 3)


def test_selection_is_a_prefix_that_stops_at_the_first_overflow():
    # 120 m budget: the 250 m segment overflows, so the 50 m segment after it
    # is not used to fill the gap even though it would fit.
    group = ranking([100, 250, 50], [0, 0, 1])
    outcome = evaluate_budget(group, 120 / 400)
    assert outcome.selected_segments == 1
    assert outcome.breaks_captured == 0


def test_selected_length_never_exceeds_budget():
    rng = np.random.default_rng(0)
    for _ in range(200):
        n = int(rng.integers(1, 60))
        group = ranking(rng.uniform(1, 500, n), rng.integers(0, 2, n), scores=rng.random(n))
        outcome = evaluate_budget(group, float(rng.choice([0.01, 0.02, 0.05, 0.10, 0.5])))
        assert outcome.selected_length_m <= outcome.budget_length_m


def test_ties_are_broken_by_segment_id():
    group = ranking([100] * 4, [0, 1, 0, 0], scores=[0.5] * 4, ids=["D", "A", "C", "B"])
    # A 25% budget holds one segment; with tied scores "A" (the break) ranks first.
    assert evaluate_budget(group, 0.25).breaks_captured == 1


def test_year_without_breaks_has_undefined_capture():
    outcome = evaluate_budget(ranking([100, 100], [0, 0]), 0.5)
    assert outcome.capture is None
    assert outcome.precision == 0.0


def test_result_does_not_depend_on_input_row_order():
    group = ranking([100, 200, 300, 400], [1, 0, 1, 0], scores=[0.9, 0.1, 0.5, 0.3])
    shuffled = group.sample(frac=1, random_state=3)
    assert evaluate_budget(group, 0.4) == evaluate_budget(shuffled, 0.4)
