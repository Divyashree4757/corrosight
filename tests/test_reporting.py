import io

import numpy as np
import pandas as pd
import pypdf
import pytest

from conftest import two_runs
from src.pipeline import SourceInfo, run_analysis
from src.reporting import build_pdf, findings_frame, to_csv_bytes
from src.review import REVIEW_STATUSES, ReviewStore
from src.schema import AnalysisConfig


def pdf_text(b: bytes) -> str:
    return "\n".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(b)).pages)


def test_csv_matches_dashboard_table(demo_result):
    shown = findings_frame(demo_result)                    # the table the dashboard renders
    csv = pd.read_csv(io.BytesIO(to_csv_bytes(demo_result)))
    assert len(csv) == len(shown) == len(demo_result.findings)
    assert csv["finding_id"].tolist() == shown["finding_id"].tolist()
    for col in ["review_category", "match_status", "SYSTEM_proposed_next_step", "earlier_observation_id"]:
        assert csv[col].fillna("").astype(str).tolist() == shown[col].fillna("").astype(str).tolist(), col
    for col in ["CALCULATED_annualised_change_mm_per_yr", "CALCULATED_latest_depth_pct_wt",
                "PREDICTED_upper_scenario_depth_at_horizon_mm", "OBSERVED_later_depth_mm"]:
        np.testing.assert_allclose(csv[col].to_numpy(float), shown[col].to_numpy(float), rtol=0, atol=1e-9, equal_nan=True)
    assert csv["dataset_sha256"].iloc[0] == demo_result.fingerprint
    assert bool(csv["synthetic_data"].iloc[0]) is True


def test_csv_counts_match_summary(demo_result):
    csv = pd.read_csv(io.BytesIO(to_csv_bytes(demo_result)))
    s = demo_result.summary()
    assert csv["review_category"].value_counts().to_dict() == s["review_counts"]


def test_pdf_generated_and_consistent_with_summary(demo_result):
    b = build_pdf(demo_result, generated_utc="2026-01-01 00:00:00 UTC")
    assert b[:4] == b"%PDF"
    txt = pdf_text(b)
    s = demo_result.summary()
    assert "CorroSight Evidence Passport" in txt and "SYNTHETIC" in txt
    assert f"Review first: {s['review_counts']['Review first']}" in txt
    top = demo_result.findings.iloc[0]
    assert top["track_id"] in txt and str(top["obs_b"]) in txt
    assert "2026-01-01 00:00:00 UTC" in txt
    assert "not a certified" in txt.lower() or "prototype" in txt.lower()
    assert "Qualified reviewer name" in txt


def test_review_decisions_flow_into_exports(demo_result, tmp_path):
    store = ReviewStore(tmp_path / "log.json")
    tid = demo_result.findings.iloc[0]["track_id"]
    store.record(demo_result.fingerprint, tid, "Requires further assessment",
                 "Perform a more detailed assessment (engineer-selected method)",
                 demo_result.findings.iloc[0]["proposed_next_step"], reviewer="A. Engineer", notes="check weld")
    latest = store.latest(demo_result.fingerprint)
    csv = pd.read_csv(io.BytesIO(to_csv_bytes(demo_result, latest)))
    row = csv[csv["finding_id"] == tid].iloc[0]
    assert row["review_status"] == "Requires further assessment" and row["reviewer"] == "A. Engineer"
    assert row["SYSTEM_proposed_next_step"] != row["REVIEWER_selected_next_step"]  # kept separate
    txt = pdf_text(build_pdf(demo_result, latest, store.history(demo_result.fingerprint), detail_ids=[tid]))
    assert "A. Engineer" in txt and "check weld" in txt
    # persistence across instances, isolation across datasets
    assert ReviewStore(tmp_path / "log.json").latest(demo_result.fingerprint)[tid]["notes"] == "check weld"
    assert ReviewStore(tmp_path / "log.json").latest("other-dataset") == {}


def test_review_store_has_no_approval_status(tmp_path):
    assert not any("approv" in s.lower() for s in REVIEW_STATUSES)
    with pytest.raises(ValueError):
        ReviewStore(tmp_path / "x.json").record("fp", "T1", "Approved", "", "")


def test_exports_reflect_uploaded_data_not_demo():
    df = two_runs([dict(axial_position_m=10, depth_mm=1.0)], [dict(axial_position_m=10, depth_mm=1.2),
                                                                dict(axial_position_m=50, depth_mm=2.0)])
    res = run_analysis(df, SourceInfo("Uploaded", ["a.csv", "b.csv"], False), AnalysisConfig(align_runs=False))
    csv = pd.read_csv(io.BytesIO(to_csv_bytes(res)))
    assert len(csv) == 2 and set(csv["later_observation_id"]) == {"RB-001", "RB-002"}
    assert not bool(csv["synthetic_data"].iloc[0])
    txt = pdf_text(build_pdf(res))
    assert "SYNTHETIC DEMO DATA" not in txt and "RB-002" in txt and "A16-" not in txt
