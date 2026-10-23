import numpy as np
import pytest

from conftest import two_runs
from src.matching import match_runs
from src.prediction import compute_growth
from src.schema import AnalysisConfig
from src.uncertainty import classify_change, combined_sigma, fit_shrinkage
from src.validation import validate

DT = 2557 / 365.25  # 2016-01-01 -> 2023-01-01, hand calculated: 2557 days


def growth(rows_a, rows_b, cfg=None):
    cfg = cfg or AnalysisConfig(align_runs=False)
    v = validate(two_runs(rows_a, rows_b))
    m = match_runs(v.data, "RA", "RB", cfg)
    G, fit, extra = compute_growth(v.data, m, cfg)
    return G.set_index("obs_a", drop=False), extra


def test_hand_calculated_example_from_brief():
    G, _ = growth([dict(axial_position_m=120.5, depth_mm=2.0)], [dict(axial_position_m=120.6, depth_mm=2.8)])
    r = G.loc["RA-001"]
    assert r["dt_years"] == pytest.approx(DT)
    assert r["delta_mm"] == pytest.approx(0.8)
    assert r["rate_mm_per_yr"] == pytest.approx(0.8 / DT)          # ~0.114 mm/yr
    assert r["rate_mm_per_yr"] == pytest.approx(0.1143, abs=5e-4)
    # sigma = sqrt(0.3^2+0.3^2) = 0.4243; 0.8 < 2*0.4243 -> within noise -> only upper scenario
    assert r["sigma_delta_mm"] == pytest.approx(np.sqrt(0.18))
    assert r["change_class"] == "WITHIN_NOISE"
    assert r["forecast_status"] == "UPPER_ONLY"
    assert np.isnan(r["proj_depth_central_mm"])
    assert r["proj_rate_upper"] == pytest.approx((0.8 + 2 * np.sqrt(0.18)) / DT)


def test_growth_beyond_noise_gives_central_projection_and_threshold_time():
    G, _ = growth([dict(axial_position_m=100, depth_mm=2.0)], [dict(axial_position_m=100, depth_mm=3.0)])
    r = G.loc["RA-001"]
    rate = 1.0 / DT
    assert r["change_class"] == "INCREASE_BEYOND_NOISE"
    assert r["forecast_status"] == "CENTRAL_AND_UPPER"
    assert r["proj_depth_central_mm"] == pytest.approx(3.0 + rate * 5)
    assert r["proj_pct_central"] == pytest.approx((3.0 + rate * 5) / 10 * 100)
    # threshold 50% of 10 mm = 5 mm; (5 - 3) / rate
    assert r["yrs_to_threshold_central"] == pytest.approx(2.0 / rate)


def test_negative_change_is_preserved_not_clamped():
    G, _ = growth([dict(axial_position_m=100, depth_mm=2.8)], [dict(axial_position_m=100, depth_mm=2.5)])
    r = G.loc["RA-001"]
    assert r["delta_mm"] == pytest.approx(-0.3)
    assert r["rate_mm_per_yr"] < 0
    assert r["change_class"] == "WITHIN_NOISE"


def test_large_decrease_is_anomalous_and_not_forecast():
    G, _ = growth([dict(axial_position_m=100, depth_mm=3.0)], [dict(axial_position_m=100, depth_mm=1.5)])
    r = G.loc["RA-001"]
    assert r["change_class"] == "DECREASE_BEYOND_NOISE"
    assert r["forecast_status"] == "NOT_ESTABLISHED"
    assert "decreased" in r["forecast_reason"]


def test_unknown_uncertainty_gives_no_interval_and_no_forecast():
    G, _ = growth([dict(axial_position_m=100, depth_mm=2.0, depth_uncertainty_mm=None)],
                  [dict(axial_position_m=100, depth_mm=3.5)])
    r = G.loc["RA-001"]
    assert r["delta_mm"] == pytest.approx(1.5)
    assert np.isnan(r["sigma_delta_mm"]) and np.isnan(r["rate_low"])
    assert r["change_class"] == "UNCERTAINTY_UNKNOWN"
    assert r["forecast_status"] == "NOT_ESTABLISHED"


def test_ambiguous_match_is_not_forecast():
    G, _ = growth([dict(axial_position_m=100.0, depth_mm=2.0), dict(axial_position_m=100.2, depth_mm=2.0)],
                  [dict(axial_position_m=100.1, depth_mm=3.5), dict(axial_position_m=100.25, depth_mm=3.5)])
    assert (G["match_status"] == "AMBIGUOUS").all()
    assert (G["forecast_status"] == "NOT_ESTABLISHED").all()
    assert G["forecast_reason"].str.contains("Match unresolved").all()


def test_new_detection_has_no_rate():
    v = validate(two_runs([dict(axial_position_m=100, depth_mm=2.0)], [dict(axial_position_m=900, depth_mm=2.0)]))
    m = match_runs(v.data, "RA", "RB", AnalysisConfig(align_runs=False))
    G, _, _ = compute_growth(v.data, m)
    new = G[G["match_status"] == "NEW_LATER"].iloc[0]
    assert np.isnan(new["rate_mm_per_yr"]) and new["forecast_status"] == "NOT_ESTABLISHED"
    assert new["latest_pct_wt"] == pytest.approx(20.0)


def test_suspicious_change_flagged():
    G, extra = growth([dict(axial_position_m=100, depth_mm=1.0)], [dict(axial_position_m=100, depth_mm=7.0)])
    assert bool(G.loc["RA-001", "suspicious_change"])
    assert extra and extra[0]["code"] == "SUSPICIOUS_CHANGE"


def test_wall_thickness_missing_blocks_pct_but_not_change():
    G, _ = growth([dict(axial_position_m=100, depth_mm=2.0, nominal_wt_mm=None)],
                  [dict(axial_position_m=100, depth_mm=3.0, nominal_wt_mm=None)])
    r = G.loc["RA-001"]
    assert r["delta_mm"] == pytest.approx(1.0)
    assert np.isnan(r["latest_pct_wt"]) and np.isnan(r["yrs_to_threshold_upper"])


def test_uncertainty_helpers():
    assert combined_sigma(0.3, 0.4) == pytest.approx(0.5)
    assert np.isnan(combined_sigma(0.3, np.nan))
    assert list(classify_change([1.0, 0.1, -1.0, 0.5], [0.4, 0.4, 0.4, np.nan])) == [
        "INCREASE_BEYOND_NOISE", "WITHIN_NOISE", "DECREASE_BEYOND_NOISE", "UNCERTAINTY_UNKNOWN"]


def test_shrinkage_pulls_noisy_rates_toward_population_mean():
    rng = np.random.default_rng(0)
    true = rng.normal(0.1, 0.05, 300)
    sig = np.full(300, 0.08)
    obs = true + rng.normal(0, sig)
    fit = fit_shrinkage(obs, sig)
    post, sd = fit.posterior(obs, sig)
    assert fit.fitted and abs(fit.mu - 0.1) < 0.02
    assert np.all(np.abs(post - fit.mu) <= np.abs(obs - fit.mu) + 1e-12)
    assert np.all(sd < sig)
    assert np.sqrt(np.mean((post - true) ** 2)) < np.sqrt(np.mean((obs - true) ** 2))


def test_shrinkage_not_fitted_with_few_points():
    assert not fit_shrinkage([0.1, 0.2], [0.05, 0.05]).fitted


def test_demo_growth_evaluation_reports_real_metrics(demo_result):
    eg = demo_result.evaluation["growth"]
    assert eg["n"] > 50
    for m in ("baseline", "shrinkage"):
        assert eg[m]["rmse"] >= eg[m]["mae"] >= 0
    assert 0 <= eg["baseline_interval_coverage"] <= 1
