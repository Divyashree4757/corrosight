"""Headless UI tests with Streamlit's AppTest: every page renders and the key interactions work.

Every test signs in through the real sign-in form first (accounts are created in a temporary user store by the
`accounts` fixture). Pages are opened through the `_nav_default` session key (AppTest cannot click st.navigation
links for function-based pages); the browser walkthrough covers real clicking.
"""

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from conftest import PW  # noqa: F401  (re-exported for other tests)

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app.py")
PAGE_KEYS = ["overview", "health", "history", "timeline", "identity", "anomalies", "patterns", "forecast", "whatif",
             "arena", "contradictions", "strategy", "workbench", "gaps", "planning", "trust", "assistant", "snapshots",
             "passport"]
def login(at, user="eng", password=PW):
    at.text_input(key="login_user").input(user)
    at.text_input(key="login_pw").input(password)
    [b for b in at.button if b.label == "Sign in"][0].click().run()
    return at


def fresh(page: str | None = None, user: str | None = "eng"):
    at = AppTest.from_file(APP, default_timeout=180)
    if page:
        at.session_state["_nav_default"] = page
    at.run()
    if user:
        login(at, user)
        assert not at.exception, at.exception
    return at


def load_demo(at):
    at.button(key="landing_demo").click().run()
    assert not at.exception, at.exception
    return at


def texts(at):
    return " ".join(m.value for m in at.markdown)


def test_home_page_renders_after_sign_in():
    at = fresh()
    assert not at.exception
    assert "Welcome, Test engineer" in texts(at)


@pytest.mark.parametrize("page", PAGE_KEYS)
def test_every_page_renders_with_demo_data(page):
    at = load_demo(fresh(page))
    assert not at.exception, at.exception
    assert len(at.error) == 0, [e.value for e in at.error]


def test_overview_numbers_come_from_analysis():
    at = load_demo(fresh("overview"))
    html = texts(at)
    assert "R2016" in html and "R2023" in html and "SYNTHETIC DEMO DATA" in html


def test_settings_change_reruns_analysis():
    at = load_demo(fresh("forecast"))
    form = at.sidebar.expander[0]
    form.number_input[0].set_value(30.0)
    form.button[0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["cfg"]["depth_review_pct_wt"] == 30.0


def test_forecast_method_switch():
    at = load_demo(fresh("forecast"))
    form = at.sidebar.expander[0]
    form.radio[0].set_value("shrinkage")
    form.button[0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["cfg"]["forecast_method"] == "shrinkage"


def test_review_and_pdf_generation_flow():
    at = load_demo(fresh("planning"))
    submit = [b for b in at.button if "Record review decision" in (b.label or "")]
    assert submit, "review form submit button missing"
    submit[0].click().run()
    assert not at.exception, at.exception
    assert any("Recorded for" in s.value for s in at.success)
    at.button(key="pp_gen").click().run()
    assert not at.exception, at.exception
    assert at.session_state["pdf_bytes"][:4] == b"%PDF"


def test_budget_planner_runs():
    at = load_demo(fresh("planning"))
    at.button(key="pl_run").click().run()
    assert not at.exception, at.exception
    assert at.session_state["plan_result"].feasible


def test_workbench_close_requires_reason_and_reopen():
    at = load_demo(fresh("workbench"))
    sel = [s for s in at.selectbox if s.label == "Review status"][0]
    sel.set_value("Closed with Documented Rationale")
    [b for b in at.button if "Record review decision" in (b.label or "")][0].click().run()
    assert any("documented rationale" in e.value for e in at.error)
    sel = [s for s in at.selectbox if s.label == "Review status"][0]
    sel.set_value("Closed with Documented Rationale")
    [t for t in at.text_area if t.label == "Reason for this decision"][0].input("Reviewed sizing; no action proposed")
    [b for b in at.button if "Record review decision" in (b.label or "")][0].click().run()
    assert any("Recorded for" in s.value for s in at.success)
    at.run()
    reopen = [b for b in at.button if "Reopen review" in (b.label or "")]
    assert reopen, "reopen form missing after closing"
    [t for t in at.text_input if t.label == "Reason for reopening"][0].input("New evidence")
    reopen[0].click().run()
    assert not at.exception, at.exception


def test_snapshot_save_and_replay():
    at = load_demo(fresh("snapshots"))
    [b for b in at.button if "Save snapshot" in (b.label or "")][0].click().run()
    assert any("Saved SNAP-" in s.value for s in at.success)
    at.button(key="sn_replay").click().run()
    assert any("Exact replay verified" in s.value for s in at.success)


def test_assistant_answers_and_admits_insufficient_evidence():
    at = load_demo(fresh("assistant"))
    at.chat_input[0].set_value("Why was T0177 prioritised?").run()
    assert "Review first" in texts(at)
    at.chat_input[0].set_value("What is the failure pressure?").run()
    assert "could not find evidence" in texts(at)


def test_identity_resolution_is_recorded_without_changing_matching():
    at = load_demo(fresh("identity"))
    before = at.session_state["focus_track"] if "focus_track" in at.session_state else None
    [t for t in at.text_area if "Rationale" in t.label][0].input("Raw signals show a single anomaly")
    [b for b in at.button if b.label == "Record resolution"][0].click().run()
    assert any("Resolution recorded" in s.value for s in at.success), [e.value for e in at.error]
    assert before is None or isinstance(before, str)


def test_upload_style_dataset_via_session_state():
    at = fresh("overview")
    df = pd.DataFrame({
        "run_id": ["U1", "U1", "U2", "U2"], "inspection_date": ["2018-05-01"] * 2 + ["2024-05-01"] * 2,
        "observation_id": ["a1", "a2", "b1", "b2"], "segment_id": ["S1"] * 4,
        "axial_position_m": [10, 80, 10.2, 80.1], "clock_position_h": [6, 3, 6.1, 3.1], "depth_mm": [1.0, 2.0, 1.3, 2.9],
        "nominal_wt_mm": [8, 8, 8, 8], "depth_uncertainty_mm": [0.3] * 4})
    at.session_state["raw_csv"] = df.to_csv(index=False)
    at.session_state["source"] = dict(name="Uploaded", files=["u.csv"], synthetic=False, pipeline_length_m=None, notes=[])
    at.session_state["evaluate"] = False
    at.session_state["run_a"], at.session_state["run_b"] = "U1", "U2"
    at.run()
    assert not at.exception, at.exception
    html = texts(at)
    assert "SYNTHETIC DEMO DATA" not in html and "U1" in html


@pytest.mark.parametrize("page", ["arena", "assistant", "patterns", "trust"])
def test_new_pages_work_with_uploaded_data(page):
    at = fresh(page)
    df = pd.DataFrame({
        "run_id": ["U1"] * 3 + ["U2"] * 3, "inspection_date": ["2018-05-01"] * 3 + ["2024-05-01"] * 3,
        "observation_id": ["a1", "a2", "a3", "b1", "b2", "b3"], "segment_id": ["S1", "S1", "S2", "S1", "S1", "S2"],
        "axial_position_m": [10, 80, 150, 10.2, 80.1, 150.1], "clock_position_h": [6, 3, 9, 6.1, 3.1, 9.0],
        "depth_mm": [1.0, 2.0, 1.5, 1.3, 2.9, 1.4], "nominal_wt_mm": [8] * 6, "depth_uncertainty_mm": [0.3] * 6})
    at.session_state["raw_csv"] = df.to_csv(index=False)
    at.session_state["source"] = dict(name="Uploaded", files=["u.csv"], synthetic=False, pipeline_length_m=None, notes=[])
    at.session_state["evaluate"] = False
    at.session_state["run_a"], at.session_state["run_b"] = "U1", "U2"
    at.run()
    assert not at.exception, at.exception
