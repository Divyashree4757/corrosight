import numpy as np

from conftest import two_runs
from src.matching import match_runs
from src.schema import AnalysisConfig
from src.validation import validate

CFG_NOALIGN = AnalysisConfig(align_runs=False)


def run(rows_a, rows_b, cfg=CFG_NOALIGN):
    v = validate(two_runs(rows_a, rows_b))
    return match_runs(v.data, "RA", "RB", cfg)


def status(m, obs_a=None, obs_b=None):
    T = m.tracks
    if obs_a:
        return T.loc[T["obs_a"] == obs_a, "match_status"].iloc[0]
    return T.loc[T["obs_b"] == obs_b, "match_status"].iloc[0]


def test_small_position_shift_matches_and_is_explained():
    a = [dict(axial_position_m=p, depth_mm=2.0) for p in (100, 200, 300)]
    b = [dict(axial_position_m=p + 0.3, depth_mm=2.4) for p in (100, 200, 300)]
    m = run(a, b)
    assert m.status_counts()["LIKELY_MATCH"] == 3
    t = m.tracks.iloc[0]
    assert t["obs_a"] == "RA-001" and t["obs_b"] == "RB-001"
    assert "Aligned axial difference" in t["rationale"] and np.isclose(t["d_pos_raw_m"], 0.3)


def test_alignment_removes_systematic_odometer_offset():
    a = [dict(axial_position_m=10 + 20 * k, depth_mm=2.0) for k in range(5)]
    b = [dict(axial_position_m=10 + 20 * k + 0.7, depth_mm=2.0) for k in range(5)]
    m = run(a, b, AnalysisConfig(align_runs=True))
    assert np.isclose(m.offsets["offset_m"].iloc[0], 0.7)
    assert np.allclose(m.tracks["d_pos_aligned_m"], 0.0, atol=1e-9)


def test_ambiguous_candidates_are_flagged_not_forced():
    a = [dict(axial_position_m=100.00, depth_mm=2.0), dict(axial_position_m=100.20, depth_mm=2.0)]
    b = [dict(axial_position_m=100.10, depth_mm=2.2), dict(axial_position_m=100.25, depth_mm=2.2)]
    m = run(a, b)
    assert m.status_counts()["AMBIGUOUS"] == 2
    assert "AMBIGUOUS" in m.tracks.iloc[0]["rationale"]
    assert m.tracks.iloc[0]["n_alternatives"] >= 1


def test_unmatched_earlier_and_new_later_are_preserved():
    a = [dict(axial_position_m=100, depth_mm=2.0), dict(axial_position_m=500, depth_mm=2.0)]
    b = [dict(axial_position_m=100.1, depth_mm=2.0), dict(axial_position_m=900, depth_mm=1.0)]
    m = run(a, b)
    assert status(m, obs_a="RA-002") == "UNMATCHED_EARLIER"
    assert status(m, obs_b="RB-002") == "NEW_LATER"
    assert len(m.tracks) == 3


def test_one_to_one_assignment_no_double_use():
    a = [dict(axial_position_m=100, depth_mm=2.0)]
    b = [dict(axial_position_m=100.05, depth_mm=2.0), dict(axial_position_m=100.6, depth_mm=2.0)]
    m = run(a, b)
    paired = m.tracks[m.tracks["match_status"].isin(["LIKELY_MATCH", "AMBIGUOUS"])]
    assert len(paired) == 1 and paired.iloc[0]["obs_b"] == "RB-001"
    assert status(m, obs_b="RB-002") == "NEW_LATER"
    assert paired["obs_b"].is_unique and paired["obs_a"].is_unique


def test_clock_gate_prevents_match():
    a = [dict(axial_position_m=100, depth_mm=2.0, clock_position_h=3.0)]
    b = [dict(axial_position_m=100, depth_mm=2.0, clock_position_h=6.5)]
    m = run(a, b)
    assert m.status_counts()["LIKELY_MATCH"] == 0


def test_clock_wraps_around_twelve():
    a = [dict(axial_position_m=100, depth_mm=2.0, clock_position_h=11.8)]
    b = [dict(axial_position_m=100, depth_mm=2.0, clock_position_h=0.1)]
    m = run(a, b)
    assert m.status_counts()["LIKELY_MATCH"] == 1


def test_depth_is_not_used_for_matching():
    a = [dict(axial_position_m=100, depth_mm=1.0)]
    b = [dict(axial_position_m=100.05, depth_mm=6.0)]
    assert run(a, b).status_counts()["LIKELY_MATCH"] == 1


def test_run_order_is_normalised_earlier_to_later():
    v = validate(two_runs([dict(axial_position_m=100, depth_mm=2.0)], [dict(axial_position_m=100, depth_mm=2.5)]))
    m = match_runs(v.data, "RB", "RA")
    assert (m.run_a, m.run_b) == ("RA", "RB")


def test_excluded_records_remain_visible():
    v = validate(two_runs([dict(axial_position_m=None, depth_mm=2.0)], [dict(axial_position_m=100, depth_mm=2.0)]))
    m = match_runs(v.data, "RA", "RB")
    assert m.status_counts()["EXCLUDED"] == 1


def test_demo_matching_metrics_are_computed_against_hidden_truth(demo_result):
    ev = demo_result.evaluation["matching"]
    assert 0 <= ev["recall_all_assigned"] <= 1
    assert ev["likely"]["precision"] >= 0.95       # regression guard on synthetic data only
    assert ev["recall_all_assigned"] >= 0.90
    counts = demo_result.match.status_counts()
    assert counts["AMBIGUOUS"] > 0 and counts["NEW_LATER"] > 0 and counts["UNMATCHED_EARLIER"] > 0
