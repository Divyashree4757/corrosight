import numpy as np

from conftest import two_runs
from src.pipeline import SourceInfo, run_analysis
from src.schema import AnalysisConfig

SRC = SourceInfo("test", ["t.csv"], False)
CFG = AnalysisConfig(align_runs=False)


def analyse(rows_a, rows_b, cfg=CFG):
    res = run_analysis(two_runs(rows_a, rows_b), SRC, cfg)
    return res, res.findings.set_index("obs_a", drop=False)


# ------------------------------------------------------------ readiness ----
def test_missing_engineering_inputs_reported():
    _, F = analyse([dict(axial_position_m=100, depth_mm=2.0, smys_mpa=None, maop_kpa=None)],
                   [dict(axial_position_m=100, depth_mm=2.2, smys_mpa=None, maop_kpa=None)])
    r = F.loc["RA-001"]
    assert r["readiness"] == "MISSING_INPUTS"
    assert "Pipe grade / SMYS" in r["inputs_missing"] and "Operating pressure (MAOP)" in r["inputs_missing"]


def test_inputs_present_but_never_claims_assessment_done():
    _, F = analyse([dict(axial_position_m=100, depth_mm=2.0)], [dict(axial_position_m=100, depth_mm=2.2)])
    r = F.loc["RA-001"]
    assert r["readiness"] == "INPUTS_PRESENT"
    assert "not performed" in r["readiness_label"]
    assert "always required" in r["requires_verification"]


def test_ambiguous_match_requires_verification():
    _, F = analyse([dict(axial_position_m=100.0, depth_mm=2.0), dict(axial_position_m=100.2, depth_mm=2.0)],
                   [dict(axial_position_m=100.1, depth_mm=2.1), dict(axial_position_m=100.25, depth_mm=2.1)])
    assert (F["readiness"] == "VERIFY").all()
    assert F["requires_verification"].str.contains("ambiguous").all()


# --------------------------------------------------------- prioritisation ----
def test_deep_defect_reviewed_first_with_traceable_explanation():
    _, F = analyse([dict(axial_position_m=100, depth_mm=4.4)], [dict(axial_position_m=100, depth_mm=4.6)])
    r = F.loc["RA-001"]
    assert r["review_category"] == "Review first"
    assert "C1" in r["condition_reasons"] and "RB-001" in r["condition_reasons"] and "46%" in r["condition_reasons"]
    assert r["proposed_next_step"] == "Send for engineering review"


def test_fast_growth_beyond_noise_reviewed_first():
    _, F = analyse([dict(axial_position_m=100, depth_mm=1.0)], [dict(axial_position_m=100, depth_mm=3.0)])
    r = F.loc["RA-001"]
    assert r["review_category"] == "Review first" and "C3" in r["condition_reasons"]


def test_routine_when_no_rule_triggered():
    _, F = analyse([dict(axial_position_m=100, depth_mm=1.0)], [dict(axial_position_m=100, depth_mm=1.1)])
    r = F.loc["RA-001"]
    assert r["review_category"] == "Routine review"
    assert r["priority_explanation"].startswith("No demo review rule triggered")


def test_missing_wall_thickness_never_lowers_concern():
    base = dict(axial_position_m=100, depth_mm=1.0)
    _, F_ok = analyse([base], [dict(axial_position_m=100, depth_mm=1.1)])
    _, F_missing = analyse([dict(base, nominal_wt_mm=None)], [dict(axial_position_m=100, depth_mm=1.1, nominal_wt_mm=None)])
    assert F_missing.loc["RA-001", "review_rank"] < F_ok.loc["RA-001", "review_rank"]
    assert F_missing.loc["RA-001", "review_category"] == "Additional data needed"
    assert "nominal wall thickness" in F_missing.loc["RA-001", "missing_inputs"]
    # a high-condition finding with missing WT stays at the top category
    _, F_fast = analyse([dict(axial_position_m=100, depth_mm=1.0, nominal_wt_mm=None)],
                        [dict(axial_position_m=100, depth_mm=3.0, nominal_wt_mm=None)])
    assert F_fast.loc["RA-001", "review_category"] == "Review first"
    assert F_fast.loc["RA-001", "evidence_quality"] == "Limited"


def test_missing_uncertainty_raises_to_additional_data():
    _, F = analyse([dict(axial_position_m=100, depth_mm=1.0, depth_uncertainty_mm=None)],
                   [dict(axial_position_m=100, depth_mm=1.1)])
    r = F.loc["RA-001"]
    assert r["review_category"] == "Additional data needed" and "E9" in r["evidence_reasons"]


def test_ambiguous_match_at_least_verify():
    _, F = analyse([dict(axial_position_m=100.0, depth_mm=1.0), dict(axial_position_m=100.2, depth_mm=1.0)],
                   [dict(axial_position_m=100.1, depth_mm=1.1), dict(axial_position_m=100.25, depth_mm=1.1)])
    assert (F["review_rank"] <= 2).all()
    assert F["evidence_reasons"].str.contains("E1").all()


def test_every_finding_has_explanation_and_next_step(demo_result):
    F = demo_result.findings
    assert F["priority_explanation"].str.len().min() > 10
    assert F["proposed_next_step"].str.len().min() > 5
    assert F["priority_order"].tolist() == list(range(1, len(F) + 1))
    assert F["review_rank"].is_monotonic_increasing
    # condition and evidence axes reported separately for every finding
    assert F["condition_level"].notna().all() and F["evidence_quality"].notna().all()


def test_demo_has_every_category(demo_result):
    cats = set(demo_result.findings["review_category"])
    assert cats == {"Review first", "Verify match / data", "Additional data needed", "Monitor", "Routine review"}


def test_thresholds_are_configurable():
    rows = ([dict(axial_position_m=100, depth_mm=3.5)], [dict(axial_position_m=100, depth_mm=3.6)])
    _, F1 = analyse(*rows, cfg=AnalysisConfig(align_runs=False, depth_review_pct_wt=40, screening_threshold_pct_wt=80))
    _, F2 = analyse(*rows, cfg=AnalysisConfig(align_runs=False, depth_review_pct_wt=30, screening_threshold_pct_wt=80))
    assert F1.loc["RA-001", "review_category"] != "Review first"
    assert F2.loc["RA-001", "review_category"] == "Review first"
    assert np.isfinite(F2.loc["RA-001", "latest_pct_wt"])
