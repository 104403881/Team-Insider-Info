import pandas as pd
import pytest

from src.modeling.config import PRIMARY_BUDGET, budget_key
from src.modeling.evaluate import prepare_panel
from src.modeling.stress import SCENARIOS, run_stress_tests

KEY = budget_key(PRIMARY_BUDGET)


@pytest.fixture(scope="module")
def stress(pipe_year):
    return run_stress_tests(prepare_panel(pipe_year), [2022, 2023])


def test_every_scenario_reports_every_candidate(stress):
    assert set(stress["scenarios"]) == set(SCENARIOS)
    for scenario in stress["scenarios"].values():
        assert set(scenario["methods"]) == {"oldest", "prior_breaks", "lookup", "logistic"}
        for entry in scenario["methods"].values():
            assert 0 <= entry[f"capture_at_{KEY}"] <= 1
            overlap = entry[f"selection_overlap_at_{KEY}"]
            assert overlap is None or 0 <= overlap <= 1


def test_untouched_inputs_leave_prior_breaks_unchanged(stress):
    # prior_break_count is never corrupted, so the prior-breaks ranking must not move.
    for scenario in stress["scenarios"].values():
        entry = scenario["methods"]["prior_breaks"]
        assert entry[f"capture_at_{KEY}_change"] == 0
        assert entry["spearman_rank_corr"] == pytest.approx(1.0)
        assert entry[f"selection_overlap_at_{KEY}"] == pytest.approx(1.0)


def test_unseen_materials_are_downgraded_to_low_confidence(stress):
    scenario = stress["scenarios"]["unseen_material_05"]
    assert scenario["affected_rows"] > 0
    assert scenario["affected_rows_confidence"]["LOW"] == 1.0


def test_masked_material_or_age_is_downgraded(stress):
    assert stress["scenarios"]["mask_10"]["affected_rows_confidence"]["LOW"] > 0


def test_metrics_carry_robustness_with_a_champion_alias(evaluation):
    robustness = evaluation.metrics["robustness"]
    champion = evaluation.metrics["champion_method"]
    for scenario in robustness["scenarios"].values():
        assert scenario["methods"]["champion"] == scenario["methods"][champion]


def test_stress_does_not_mutate_the_panel(pipe_year):
    panel = prepare_panel(pipe_year)
    before = panel.copy()
    run_stress_tests(panel, [2023], methods=["oldest"])
    pd.testing.assert_frame_equal(panel, before)
