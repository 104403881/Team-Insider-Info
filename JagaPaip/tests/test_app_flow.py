"""End-to-end checks through Streamlit's AppTest runner."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")
PAGES = ["Overview", "Risk Worklist", "Pipe Evidence", "Proof Mode", "Evaluation & Data Quality"]


def start(page=None):
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    if page:
        at.sidebar.radio(key="page").set_value(page).run()
    return at


def text(at):
    extras = []
    for name in ("info", "warning", "error", "success"):
        extras.extend(item.value for item in getattr(at, name, []))
    return " ".join([item.value for item in at.markdown] + [item.value for item in at.caption] + extras)


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_without_exceptions(page):
    at = start(page)
    assert not at.exception
    page_text = text(at)
    assert "DEMO DATA" in page_text or "Kitchener" in page_text or "demonstrator" in page_text.lower()


def test_budget_slider_rebuilds_the_overview_plan():
    at = start("Overview")
    before = text(at)
    at.sidebar.slider(key="budget_km").set_value(0.5).run()
    after = text(at)
    assert before != after
    assert "funded of 0.50 km" in after
    at.sidebar.slider(key="budget_km").set_value(0.0).run()
    assert "No budget set" in text(at)


def test_reveal_does_not_change_either_plan():
    at = start("Proof Mode")
    page = text(at)
    assert "Outcomes are hidden" in page
    assert "Capture@" not in " ".join(m.value for m in at.markdown if "jp-kpis" in m.value and "<div" in m.value)
    plans_before = [df.value.copy() for df in at.dataframe[:2]]
    at.button(key="proof_reveal_btn").click().run()
    assert not at.exception
    assert "Plans unchanged by the reveal" in text(at)
    plans_after = [df.value for df in at.dataframe[:2]]
    for before, after in zip(plans_before, plans_after):
        assert before["Pipe ID"].tolist() == after["Pipe ID"].tolist()
    at.slider(key="proof_budget_km").set_value(2.0).run()
    assert "Outcomes are hidden" in text(at)


def test_tour_button_navigates_to_pipe_evidence():
    at = start("Overview")
    at.button(key="tour_3").click().run()
    assert at.sidebar.radio(key="page").value == "Pipe Evidence"
    assert at.selectbox(key="evidence_pipe").value
    assert not at.exception


def test_worklist_filters_and_sort_run():
    at = start("Risk Worklist")
    at.multiselect(key="wl_bands").set_value(["High"]).run()
    at.selectbox(key="wl_status").set_value("All segments").run()
    at.selectbox(key="wl_sort").set_value("Length, longest first").run()
    assert not at.exception
    lengths = at.dataframe[0].value["Length (m)"].tolist()
    assert lengths == sorted(lengths, reverse=True)
    assert set(at.dataframe[0].value["Risk band"]) == {"High"}
    table = at.dataframe[0].value
    assert {"Location", "Priority", "Evidence", "Review", "Recommended action"} <= set(table.columns)
    at.selectbox(key="wl_review").set_value("Reviewed this session").run()
    assert not at.exception
    assert "No segments match these filters" in text(at)


def test_proof_selection_toggle_and_evaluation_honesty():
    at = start("Proof Mode")
    assert "Plan composition" in text(at)
    assert "not a measured" in text(at).lower() or "Not a measured" in text(at)
    at.button(key="proof_hide_sel").click().run()
    assert not at.exception
    assert "Selections are hidden" in text(at)
    at.button(key="proof_show_sel").click().run()
    assert not at.exception
    assert at.dataframe[0].value["Pipe ID"].tolist()
    at.sidebar.radio(key="page").set_value("Evaluation & Data Quality").run()
    assert not at.exception
    page = text(at)
    assert "No genuine measured results are loaded" in page
    assert "What field validation would still require" in page
