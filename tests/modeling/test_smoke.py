"""The integration smoke test must pass good handoffs and catch each broken rule."""

import json

import numpy as np
import pandas as pd
import pytest

from src.modeling.smoke import check_contracts, contract_c_errors, run


def contract_c_from(contract_b: pd.DataFrame) -> pd.DataFrame:
    """A Contract C that follows every rule: VALIDATED_RISK rows in Contract B order."""
    frames = []
    for (_, _), group in contract_b.groupby(["test_year", "method"]):
        ranked = group.sort_values(["risk_percentile", "segment_id"], ascending=[False, True]).reset_index(drop=True)
        frames.append(
            pd.DataFrame(
                {
                    "test_year": ranked["test_year"],
                    "method": ranked["method"],
                    "ranking_mode": "VALIDATED_RISK",
                    "segment_id": ranked["segment_id"],
                    "priority_rank": np.arange(1, len(ranked) + 1),
                    "cumulative_length_m": ranked["length_m"].cumsum(),
                    "risk_percentile": ranked["risk_percentile"],
                    "risk_pattern": "Repeat-break pattern",
                    "confidence_label": ranked["confidence_label"],
                    "consequence_index": 1.0,
                    "recommended_action": np.where(ranked["confidence_label"] == "HIGH", "RENEWAL_REVIEW", "INSPECT"),
                    "reason_short": "Previous breaks increase observed recurrence risk.",
                    "actual_break": ranked["actual_break"],
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


@pytest.fixture(scope="module")
def good_c(evaluation):
    return contract_c_from(evaluation.contract_b)


def failing(errors: dict) -> dict:
    return {name: msgs for name, msgs in errors.items() if msgs}


def test_a_correct_contract_c_passes_every_decision_test(evaluation, good_c):
    assert failing(contract_c_errors(good_c, evaluation.contract_b, evaluation.metrics)) == {}


def test_reordered_contract_c_is_caught(evaluation, good_c):
    broken = good_c.copy()
    first_two = broken.index[:2]
    broken.loc[first_two, "priority_rank"] = broken.loc[first_two[::-1], "priority_rank"].to_numpy()
    assert "VALIDATED_RISK order equals Contract B" in failing(contract_c_errors(broken, evaluation.contract_b, evaluation.metrics))


def test_renewal_review_on_low_confidence_is_caught(evaluation, good_c):
    broken = good_c.copy()
    low = broken.index[broken["confidence_label"] == "LOW"][:1]
    assert len(low)
    broken.loc[low, "recommended_action"] = "RENEWAL_REVIEW"
    assert "LOW/OOD never get RENEWAL_REVIEW" in failing(contract_c_errors(broken, evaluation.contract_b, evaluation.metrics))


def test_causal_language_is_caught(evaluation, good_c):
    broken = good_c.assign(reason_short="This break was caused by corrosion.")
    assert "Risk patterns and reasons avoid causal language" in failing(
        contract_c_errors(broken, evaluation.contract_b, evaluation.metrics)
    )


def test_missing_columns_and_baselines_are_reported(evaluation, good_c):
    no_column = good_c.drop(columns=["reason_short"])
    assert "Contract C columns" in failing(contract_c_errors(no_column, evaluation.contract_b, evaluation.metrics))
    champion_only = good_c[good_c["method"] == "champion"]
    assert "Contract C has baseline rows" in failing(contract_c_errors(champion_only, evaluation.contract_b, evaluation.metrics))


def test_synthetic_results_fail_the_real_results_gate(pipe_year, evaluation):
    checks = {c.name: c.status for c in check_contracts(pipe_year, evaluation.contract_b, evaluation.metrics)}
    assert checks["Results are real, not synthetic"] == "FAIL"
    assert checks["Test years are the agreed 2023-2025"] == "WARN"
    assert checks["metrics.json reproduces Contract B counts"] == "PASS"
    assert checks["Champion matches the selection rule"] == "PASS"


def test_full_run_on_handoff_files(tmp_path, pipe_year, evaluation, good_c):
    pipe_year.to_parquet(tmp_path / "pipe_year.parquet", index=False)
    evaluation.contract_b.to_parquet(tmp_path / "fold_predictions.parquet", index=False)
    (tmp_path / "metrics.json").write_text(json.dumps(evaluation.metrics), encoding="utf-8")
    without_c = {c.name: c.status for c in run(tmp_path, app=False)}
    assert without_c["Contract C (ranked_worklists)"] == "SKIP"
    assert without_c["Contract A <-> B join (segment_id, year)"] == "PASS"
    good_c.to_parquet(tmp_path / "ranked_worklists.parquet", index=False)
    with_c = {c.name: c.status for c in run(tmp_path, app=False)}
    assert with_c["Contract C Proof Mode counts equal metrics.json"] == "PASS"
    assert with_c["VALIDATED_RISK order equals Contract B"] == "PASS"
