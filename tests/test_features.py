"""Tests for the v1.0 feature modules: anomalies, identity conflicts, contradictions, patterns, model arena,
snapshots, assistant, strategy simulator, evidence gaps, timeline, review workbench and passport extras."""

import io

import numpy as np
import pandas as pd
import pypdf
import pytest

from conftest import two_runs
from src import anomalies, assistant, contradictions, gaps, model_arena, patterns, snapshots, strategy, timeline
from src.conflicts import RESOLUTION_OPTIONS, ResolutionLog, candidate_table, conflict_overview
from src.pipeline import SourceInfo, run_analysis
from src.reporting import build_pdf, findings_frame, to_csv_bytes
from src.review import CLOSED_STATUS, LEGACY_STATUSES, ReviewStore
from src.schema import AnalysisConfig

SRC = SourceInfo("t", ["t.csv"], False)
CFG = AnalysisConfig(align_runs=False)


def analyse(a, b, cfg=CFG):
    return run_analysis(two_runs(a, b), SRC, cfg)


# ------------------------------------------------------------------ anomalies
def test_anomalies_explain_every_flag_and_never_modify_data(demo_result):
    before = demo_result.validation.data.copy()
    A = anomalies.detect(demo_result)
    pd.testing.assert_frame_equal(before, demo_result.validation.data)
    assert len(A) > 0
    for col in ("observed", "comparison", "reason", "severity", "evidence_required", "next_step"):
        assert A[col].notna().all() and (A[col].astype(str).str.len() > 0).all(), col
    assert {"DEPTH_UNIT_SUSPECT", "NON_POSITIVE_DEPTH", "POSSIBLE_DUPLICATE"} <= set(A["code"])


def test_anomaly_decrease_and_config():
    r = analyse([dict(axial_position_m=100, depth_mm=3.0)], [dict(axial_position_m=100, depth_mm=1.5)])
    A = anomalies.detect(r)
    assert "DECREASE_Z" in set(A["code"])
    r2 = analyse([dict(axial_position_m=100, depth_mm=1.0)], [dict(axial_position_m=100, depth_mm=3.0)])
    assert "LARGE_Z" in set(anomalies.detect(r2)["code"])                          # z = 2/0.42 > 3
    assert "LARGE_Z" not in set(anomalies.detect(r2, anomalies.AnomalyConfig(change_z_notable=8))["code"])


def test_correction_log_keeps_original(tmp_path):
    log = anomalies.CorrectionLog(tmp_path / "c.json")
    with pytest.raises(ValueError):
        log.propose("fp", "R1", "o1", "depth_mm", 2500.0, "2.5", "", "me")
    e = log.propose("fp", "R1", "o1", "depth_mm", 2500.0, "2.5", "unit error", "me")
    assert e["original_value"] == 2500.0 and "NOT applied" in e["status"]


# ------------------------------------------------------------------ identity conflicts
def test_candidate_table_shows_competing_claims():
    r = analyse([dict(axial_position_m=100.0, depth_mm=2.0), dict(axial_position_m=100.2, depth_mm=2.0)],
                [dict(axial_position_m=100.1, depth_mm=2.1), dict(axial_position_m=100.25, depth_mm=2.1)])
    tid = r.findings["track_id"].iloc[0]
    CT = candidate_table(r, tid)
    assert len(CT) >= 2 and CT["algorithm_assigned"].sum() == 1
    assert (CT["competing_claim"].str.len() > 0).any()
    assert CT["supports"].str.len().min() > 0 and CT["opposes"].str.len().min() > 0
    O = conflict_overview(r)
    assert set(O["group"]) == {"Ambiguous"}


def test_resolution_does_not_change_matching(tmp_path, demo_result):
    before = demo_result.match.tracks.copy()
    log = ResolutionLog(tmp_path / "r.json")
    log.propose(demo_result.fingerprint, "T0163", "a -> b", "Ambiguous match", RESOLUTION_OPTIONS[2], "", "single anomaly", "me")
    pd.testing.assert_frame_equal(before, demo_result.match.tracks)
    with pytest.raises(ValueError):
        log.propose("fp", "T1", "a", "b", "made up", "", "x", "me")


# ------------------------------------------------------------------ contradictions
def test_contradiction_rules_fire_on_constructed_cases():
    r = analyse([dict(axial_position_m=100, depth_mm=3.0)], [dict(axial_position_m=100, depth_mm=1.5)])
    K = contradictions.find(r)
    assert "K5" in set(K["rule"])
    row = K[K["rule"] == "K5"].iloc[0]
    assert "3.00" in row["evidence_a"] and "1.50" in row["evidence_b"] and row["resolve_with"]
    r2 = analyse([dict(axial_position_m=100.0, depth_mm=4.5), dict(axial_position_m=100.2, depth_mm=4.5)],
                 [dict(axial_position_m=100.1, depth_mm=4.6), dict(axial_position_m=100.25, depth_mm=4.6)])
    assert "K1" in set(contradictions.find(r2)["rule"])


def test_reviewer_disagreement_and_resolution_rules():
    r = analyse([dict(axial_position_m=100, depth_mm=1.0)], [dict(axial_position_m=100, depth_mm=1.1)])
    tid = r.findings["track_id"].iloc[0]
    hist = [dict(track_id=tid, reviewer="A", status="Reviewed", reviewer_selected_next_step="x"),
            dict(track_id=tid, reviewer="B", status="Additional Evidence Required", reviewer_selected_next_step="y")]
    res = {tid: dict(resolution="Treat as separate defects (no match)", algorithm_pairing="a -> b",
                     algorithm_status="Likely match", reviewer="B")}
    K = contradictions.find(r, hist, res)
    assert {"K7", "K8"} <= set(K["rule"])


# ------------------------------------------------------------------ patterns
def test_spatial_clusters_and_association(demo_result):
    F = demo_result.findings.copy()
    CL, labels = patterns.spatial_clusters(F, gap_m=15, min_size=4)
    assert len(CL) > 0 and (CL["findings"] >= 4).all()
    assert (CL["end_m"] >= CL["start_m"]).all()
    a = patterns.association(F, "clock_band")
    assert 0 <= a["p_value"] <= 1 and "not evidence of a cause" in a["note"]
    S = patterns.segment_summary(F)
    assert S["findings"].sum() == F["segment_id"].notna().sum()


# ------------------------------------------------------------------ model arena
def test_arena_group_split_is_leak_free_and_reproducible(demo_frames, demo_result):
    _, gt = demo_frames
    a1 = model_arena.run_arena(demo_result.growth, gt, "R2016", "R2023", seeds=5)
    a2 = model_arena.run_arena(demo_result.growth, gt, "R2016", "R2023", seeds=5)
    assert a1["ok"]
    pd.testing.assert_frame_equal(a1["summary"], a2["summary"])
    S = a1["summary"].set_index("method")
    assert set(S.index) == set(model_arena.METHODS)
    assert (S["rmse"] >= S["mae"]).all() and S["coverage"].between(0, 1).all()
    E = model_arena.evaluation_frame(demo_result.growth, gt, "R2016", "R2023")
    assert E["defect"].is_unique   # one evaluated record per defect -> group split is a defect split


def test_arena_needs_enough_records():
    assert not model_arena.run_arena(pd.DataFrame(columns=["match_status"]), pd.DataFrame(
        columns=["run_id", "observation_id", "true_defect_id", "true_rate_mm_per_yr"]), "a", "b")["ok"]


# ------------------------------------------------------------------ snapshots
def test_snapshot_replay_and_compare(tmp_path, demo_frames):
    raw, _ = demo_frames
    src = SourceInfo("Demo", ["d.csv"], True, 4800.0)
    r1 = run_analysis(raw, src)
    store = snapshots.SnapshotStore(tmp_path / "s.json")
    s1 = store.save(r1, {}, "baseline")
    out = snapshots.replay(s1, raw, src, run_analysis)
    assert out["exact"] and out["status"] == "Exact replay verified"
    r2 = run_analysis(raw, src, AnalysisConfig(depth_review_pct_wt=30))
    s2 = store.save(r2, {"T0001": {"status": "Reviewed", "reviewer": "x", "timestamp_utc": "t"}}, "lower threshold")
    assert len(store.list(r1.fingerprint)) == 2 and store.get(s1["snapshot_id"])["note"] == "baseline"  # not overwritten
    C = snapshots.compare(s1, s2)
    assert (C["config"]["setting"] == "depth_review_pct_wt").any()
    assert len(C["findings"]) > 0 and len(C["reviews"]) == 1
    other = raw.copy()
    other.loc[0, "depth_mm"] = "9.99"
    assert snapshots.replay(s1, other, src, run_analysis)["status"] == "Cannot replay"


# ------------------------------------------------------------------ assistant
def test_assistant_is_grounded(demo_result):
    ctx = assistant.Context(demo_result)
    tid = demo_result.findings["track_id"].iloc[0]
    a = assistant.ask(f"Why was {tid} prioritised?", ctx)
    assert a.grounded and tid in a.text and demo_result.findings.iloc[0]["review_category"] in a.text
    assert not assistant.ask("Why T9999?", ctx).grounded
    assert not assistant.ask("What is the failure pressure?", ctx).grounded
    assert not assistant.ask("How do the forecasting methods compare?", ctx).grounded   # no arena in context
    assert not assistant.ask("anything", assistant.Context(None)).grounded


# ------------------------------------------------------------------ strategy
def test_strategy_respects_limits_and_differs(demo_result):
    A = anomalies.detect(demo_result)
    K = contradictions.find(demo_result)
    inp = strategy.StrategyInputs(budget=20000, capacity=15)
    out = strategy.simulate(demo_result.findings, A, K, inp)
    R = out["results"]
    for v in R.values():
        assert v["budget_used"] <= 20000 and v["findings_covered"] <= 15
    assert R["priority"]["review_first_covered"] >= R["uncertainty"]["review_first_covered"]
    assert R["uncertainty"]["uncertainty_covered"] >= R["priority"]["uncertainty_covered"]
    assert strategy.simulate(demo_result.findings, A, K, strategy.StrategyInputs(budget=0))["results"]["priority"]["findings_covered"] == 0


# ------------------------------------------------------------------ gaps and trust
def test_gaps_and_unlock(demo_result):
    G = gaps.finding_gaps(demo_result.findings)
    assert {"Missing engineering input", "Defect identity unresolved"} <= set(G["gap_type"])
    UO = gaps.unlock_opportunities(demo_result.findings)
    top = UO.iloc[0]
    F = demo_result.findings
    n = int((F["inputs_missing"] == top["data_request"]).sum())
    assert top["findings_unblocked"] == n
    T = gaps.trust_scorecard(demo_result)
    assert T["validity"][["depth_valid", "uncertainty_stated"]].le(100).all().all()


# ------------------------------------------------------------------ timeline
def test_timeline_provenance_and_revisions(demo_result):
    tid = "T0177"
    ev = timeline.build(demo_result, tid, [], [], [], [], [])
    assert set(ev["provenance"]) == {"Source record", "Derived by analysis"}
    assert not ev["event"].str.contains("Revision").any()       # no invented revisions without snapshots
    snaps = [dict(snapshot_id="S1", timestamp_utc="2026-01-01 00:00:00 UTC", findings={tid: ["Monitor", 0.1, "x", "y", 1.0]}),
             dict(snapshot_id="S2", timestamp_utc="2026-01-02 00:00:00 UTC", findings={tid: ["Review first", 0.1, "x", "y", 1.0]})]
    rev = [dict(track_id=tid, timestamp_utc="2026-01-03 00:00:00 UTC", reviewer="me", status="Reviewed",
                reviewer_selected_next_step="x", reason="ok")]
    ev2 = timeline.build(demo_result, tid, rev, [], [], snaps, [])
    assert ev2["event"].str.contains("Revision between snapshots").sum() == 1
    assert (ev2["provenance"] == "Recorded log").sum() >= 4


# ------------------------------------------------------------------ review workbench
def test_review_reopen_and_close_rules(tmp_path):
    st = ReviewStore(tmp_path / "rv.json")
    with pytest.raises(ValueError):
        st.record("fp", "T1", CLOSED_STATUS, "x", "y", "me")
    st.record("fp", "T1", CLOSED_STATUS, "x", "y", "me", reason="documented")
    st.reopen("fp", "T1", "you", "new evidence")
    h = st.history("fp", "T1")
    assert [e["status"] for e in h] == [CLOSED_STATUS, "Under Review"] and h[1]["action"] == "reopened"
    for s in LEGACY_STATUSES:                       # old logs stay valid
        st.record("fp", "T2", s, "x", "y")
    with pytest.raises(ValueError):
        st.reopen("fp", "T9", "me", "x")


# ------------------------------------------------------------------ passport extras
def test_passport_extras_consistent(demo_result):
    A = anomalies.detect(demo_result)
    K = contradictions.find(demo_result)
    ex = dict(snapshot_id="SNAP-TEST-123", anomalies=A, contradictions=K, gaps=gaps.finding_gaps(demo_result.findings, A),
              resolutions={}, corrections=[], arena=None)
    shown = findings_frame(demo_result, {}, ex)
    csv = pd.read_csv(io.BytesIO(to_csv_bytes(demo_result, {}, extras=ex)))
    assert csv["ANALYSIS_contradictions"].fillna("").tolist() == shown["ANALYSIS_contradictions"].fillna("").tolist()
    assert (csv["analysis_snapshot_id"] == "SNAP-TEST-123").all()
    tid = K["track_id"].iloc[0]
    assert K[K["track_id"] == tid]["title"].iloc[0] in shown.set_index("finding_id").at[tid, "ANALYSIS_contradictions"]
    txt = "\n".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(build_pdf(demo_result, extras=ex, detail_ids=[tid]))).pages)
    assert "SNAP-TEST-123" in txt and "Contradictions" in txt and "does not certify pipeline safety" in txt
    # base export (no extras) unchanged in shape
    assert "ANALYSIS_contradictions" not in findings_frame(demo_result).columns
    assert np.isfinite(shown["CALCULATED_annualised_change_mm_per_yr"]).any()
