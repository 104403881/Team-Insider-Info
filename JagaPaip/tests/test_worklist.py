"""Worklist display logic never changes rank or selection."""

import io

import pandas as pd

from jagapaip.demo_data import build_demo_tables
from jagapaip.proof import build_plan, network_as_of
from jagapaip.ranking import build_worklist
from jagapaip.worklist import (
    PLAN_ALL,
    PLAN_FUNDED,
    PLAN_UNFUNDED,
    REVIEW_DONE,
    REVIEW_OPEN,
    Criteria,
    add_reasons,
    annotate_worklist,
    clean_search,
    export_csv,
    filter_worklist,
    priority_reason,
)


def demo_plan(budget_m=2000):
    pipes, breaks = build_demo_tables()
    return add_reasons(build_plan(network_as_of(pipes, breaks, 2024), budget_m))


def test_filters_do_not_change_rank_or_selection():
    plan = demo_plan()
    view = filter_worklist(plan, Criteria(bands=["High", "Moderate"], plan_status=PLAN_ALL, sort="Length, longest first"))
    merged = view.merge(plan[["pipe_id", "rank", "selected"]], on="pipe_id", suffixes=("", "_orig"))
    assert (merged["rank"] == merged["rank_orig"]).all()
    assert (merged["selected"] == merged["selected_orig"]).all()
    assert set(view["risk_band"]) <= {"High", "Moderate"}
    lengths = view["length_m"].tolist()
    assert lengths == sorted(lengths, reverse=True)


def test_plan_status_and_search():
    plan = demo_plan()
    assert filter_worklist(plan, Criteria(plan_status=PLAN_FUNDED))["selected"].all()
    assert not filter_worklist(plan, Criteria(plan_status=PLAN_UNFUNDED))["selected"].any()
    one = filter_worklist(plan, Criteria(search="  jp-1018 ", plan_status=PLAN_ALL))
    assert one["pipe_id"].tolist() == ["JP-1018"]
    assert clean_search("x" * 200) == "x" * 64


def test_unknown_filter_values_are_ignored_and_regex_is_literal():
    plan = demo_plan()
    everything = filter_worklist(plan, Criteria(plan_status=PLAN_ALL))
    ignored = filter_worklist(plan, Criteria(materials=["Unobtainium"], plan_status=PLAN_ALL))
    assert len(ignored) == len(everything)
    assert filter_worklist(plan, Criteria(search=".*", plan_status=PLAN_ALL)).empty


def test_age_range_filter():
    plan = demo_plan()
    view = filter_worklist(plan, Criteria(age_range=(40, 50), plan_status=PLAN_ALL))
    assert view["age_years"].between(40, 50).all()


def test_ranking_is_deterministic_under_row_shuffles():
    pipes, breaks = build_demo_tables()
    features = network_as_of(pipes, breaks, 2024)
    baseline = build_worklist(features, 2500)
    for seed in range(5):
        shuffled = features.sample(frac=1, random_state=seed).reset_index(drop=True)
        again = build_worklist(shuffled, 2500)
        assert again["pipe_id"].tolist() == baseline["pipe_id"].tolist()
        assert again["selected"].tolist() == baseline["selected"].tolist()


def test_priority_reason_lists_inputs_not_causes():
    plan = demo_plan()
    top = plan.sort_values("rank").iloc[0]
    reason = priority_reason(top)
    assert reason.startswith("Heuristic:")
    assert "prior" in reason and "yrs" in reason
    assert "caus" not in reason.lower()
    supplied = {"score_source": "supplied_prediction", "predicted_risk": 0.71}
    assert priority_reason(supplied) == "Supplied model score 0.710"


def test_missing_values_are_handled():
    frame = pd.DataFrame(
        {
            "pipe_id": ["A", "B"],
            "material": [None, "PVC"],
            "install_year": [1970, None],
            "length_m": [100.0, 80.0],
            "age_years": [50, None],
            "historical_breaks": [pd.NA, 2],
            "decision_year": [2020, 2020],
        }
    )
    plan = add_reasons(build_worklist(frame, 200))
    assert plan["predicted_risk"].notna().all()
    reason_a = plan.loc[plan["pipe_id"] == "A", "priority_reason"].iloc[0]
    assert "break history not in source" in reason_a


def test_annotate_adds_location_priority_and_evidence_without_changing_rank():
    plan = demo_plan()
    annotated = annotate_worklist(plan, reviewed_ids={"JP-1018"})
    merged = annotated.merge(plan[["pipe_id", "rank", "selected", "predicted_risk", "risk_band", "recommended_action"]], on="pipe_id", suffixes=("", "_orig"))
    assert (merged["rank"] == merged["rank_orig"]).all()
    assert (merged["selected"] == merged["selected_orig"]).all()
    assert (merged["predicted_risk"] == merged["predicted_risk_orig"]).all()
    assert annotated["location"].notna().all()
    assert set(annotated["priority"]) <= {"P1", "P2", "P3"}
    renewal = annotated.loc[annotated["recommended_action"] == "Renewal Review"]
    if len(renewal):
        assert (renewal["priority"] == "P1").all()
    assert annotated.loc[annotated["pipe_id"] == "JP-1018", "review_status"].iloc[0] == "Reviewed"
    assert "prior" in annotated["evidence"].iloc[0]


def test_review_filter_uses_session_ids_only():
    plan = annotate_worklist(demo_plan())
    marked = {"JP-1018"}
    open_rows = filter_worklist(plan, Criteria(plan_status=PLAN_ALL, review_status=REVIEW_OPEN, reviewed_ids=marked))
    done_rows = filter_worklist(plan, Criteria(plan_status=PLAN_ALL, review_status=REVIEW_DONE, reviewed_ids=marked))
    assert "JP-1018" not in set(open_rows["pipe_id"])
    assert done_rows["pipe_id"].tolist() == ["JP-1018"]


def test_csv_export_round_trips_the_view():
    plan = demo_plan()
    view = filter_worklist(plan, Criteria(plan_status=PLAN_FUNDED))
    data = export_csv(view)
    back = pd.read_csv(io.BytesIO(data))
    assert back["pipe_id"].tolist() == view["pipe_id"].tolist()
    assert {"rank", "risk_score", "recommended_action", "length_m", "in_plan", "priority_reason", "score_source"} <= set(back.columns)
    assert back["in_plan"].all()
    assert not any(column.startswith("future") for column in back.columns)
