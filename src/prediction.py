"""Observed change, annualised rate and illustrative constant-rate projections.

Definitions (dimension analysed: reported metal-loss DEPTH in mm, not wall thickness)
-------------------------------------------------------------------------------------
* Observed change        D  = depth_later - depth_earlier                      [mm]   (Calculated)
* Elapsed time           dt = (date_later - date_earlier) / 365.25             [years]
* Annualised change      R  = D / dt                                            [mm/yr] (Calculated)
* Depth % of nominal WT  = depth / nominal_wt * 100 (only when WT is valid)     [%]    (Calculated)
* Projection (Predicted, illustrative): depth(H) = depth_later + rate * H under a CONSTANT-RATE assumption,
  for a horizon H after the later inspection. Two scenarios:
    - central: rate = observed rate (baseline) or posterior mean (shrinkage) - only when supported;
    - upper screening scenario: rate + k * sigma_rate (measurement noise only).
* Years to screening threshold = (threshold% * WT - depth_later) / rate. The threshold is a configurable
  DEMO assumption. The result is NOT a repair deadline or remaining life.

Negative changes are kept as observed. They are never clamped to zero.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .matching import MatchResult
from .schema import AnalysisConfig
from .uncertainty import CHANGE_CLASSES, ShrinkageFit, classify_change, combined_sigma, fit_shrinkage

FORECAST_STATUSES = {
    "CENTRAL_AND_UPPER": "Projection available (central + upper scenario)",
    "UPPER_ONLY": "Upper screening scenario only (growth not distinguishable from noise)",
    "NOT_ESTABLISHED": "Reliable forecast cannot be established",
}


def _rec(data: pd.DataFrame, run: str):
    sub = data[data["run_id"] == run].drop_duplicates(subset=["observation_id"], keep="first")
    return sub.set_index("observation_id")


def compute_growth(data: pd.DataFrame, mr: MatchResult, config: AnalysisConfig | None = None):
    """Return (growth_table, shrinkage_fit, extra_issues)."""
    cfg = config or AnalysisConfig()
    A, B = _rec(data, mr.run_a), _rec(data, mr.run_b)
    T = mr.tracks.copy()
    dt = mr.years_between
    k = cfg.noise_k

    def get(src, obs, col):
        if not isinstance(obs, str) or obs not in src.index:
            return np.nan
        v = src.at[obs, col]
        return v

    def flag(src, obs, col):
        v = get(src, obs, col)
        return bool(v) if not (isinstance(v, float) and np.isnan(v)) else False

    rows = []
    for r in T.itertuples():
        a, b = r.obs_a, r.obs_b
        rows.append(dict(
            segment_id=get(B, b, "segment_id") if isinstance(b, str) else get(A, a, "segment_id"),
            joint_id=get(B, b, "joint_id") if isinstance(b, str) else get(A, a, "joint_id"),
            pos_a=get(A, a, "axial_position_m"), pos_b=get(B, b, "axial_position_m"),
            clock_a=get(A, a, "clock_position_h"), clock_b=get(B, b, "clock_position_h"),
            depth_a=get(A, a, "depth_mm"), depth_b=get(B, b, "depth_mm"),
            depth_valid_a=flag(A, a, "depth_valid"),
            depth_valid_b=flag(B, b, "depth_valid"),
            length_a=get(A, a, "length_mm"), length_b=get(B, b, "length_mm"),
            width_a=get(A, a, "width_mm"), width_b=get(B, b, "width_mm"),
            wt_a=get(A, a, "nominal_wt_mm") if flag(A, a, "wt_valid") else np.nan,
            wt_b=get(B, b, "nominal_wt_mm") if flag(B, b, "wt_valid") else np.nan,
            u_a=get(A, a, "depth_uncertainty_mm") if flag(A, a, "uncertainty_known") else np.nan,
            u_b=get(B, b, "depth_uncertainty_mm") if flag(B, b, "uncertainty_known") else np.nan,
            flags_a=get(A, a, "quality_flags") if isinstance(a, str) else "",
            flags_b=get(B, b, "quality_flags") if isinstance(b, str) else "",
            od_mm=get(B, b, "outer_diameter_mm") if isinstance(b, str) else get(A, a, "outer_diameter_mm"),
            smys=get(B, b, "smys_mpa") if isinstance(b, str) else get(A, a, "smys_mpa"),
            maop=get(B, b, "maop_kpa") if isinstance(b, str) else get(A, a, "maop_kpa"),
        ))
    G = pd.concat([T.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    for c in ("flags_a", "flags_b"):
        G[c] = G[c].fillna("").astype(str).replace("nan", "")

    # wall thickness used = later record's valid WT, else earlier's
    G["wt_mm"] = G["wt_b"].where(G["wt_b"].notna(), G["wt_a"])
    G["wt_conflict"] = G["wt_a"].notna() & G["wt_b"].notna() & (np.abs(G["wt_a"] - G["wt_b"]) > 0.05)

    paired = G["match_status"].isin(["LIKELY_MATCH", "AMBIGUOUS"])
    both_depth = paired & G["depth_valid_a"] & G["depth_valid_b"]
    G["dt_years"] = np.where(paired, dt, np.nan)
    G["delta_mm"] = np.where(both_depth, G["depth_b"] - G["depth_a"], np.nan)
    G["rate_mm_per_yr"] = G["delta_mm"] / dt if dt > 0 else np.nan
    G["sigma_delta_mm"] = np.where(both_depth, combined_sigma(G["u_a"], G["u_b"]), np.nan)
    G["sigma_rate_mm_per_yr"] = G["sigma_delta_mm"] / dt if dt > 0 else np.nan
    G["change_class"] = classify_change(G["delta_mm"], G["sigma_delta_mm"], k)
    G["change_class_label"] = G["change_class"].map(CHANGE_CLASSES)
    G["rate_low"] = G["rate_mm_per_yr"] - k * G["sigma_rate_mm_per_yr"]
    G["rate_high"] = G["rate_mm_per_yr"] + k * G["sigma_rate_mm_per_yr"]
    G["suspicious_change"] = np.abs(G["rate_mm_per_yr"]) > cfg.suspicious_rate_mm_per_yr

    # latest valid evidence for each finding (for % WT and review rules)
    latest_depth = np.where(G["depth_valid_b"], G["depth_b"], np.where(G["depth_valid_a"], G["depth_a"], np.nan))
    G["latest_depth_mm"] = latest_depth
    G["latest_depth_source"] = np.where(G["depth_valid_b"], mr.run_b, np.where(G["depth_valid_a"], mr.run_a, "none"))
    G["latest_pct_wt"] = G["latest_depth_mm"] / G["wt_mm"] * 100

    # ---------------- model B: shrinkage ----------------
    fit_mask = (G["match_status"] == "LIKELY_MATCH") & np.isfinite(G["rate_mm_per_yr"]) & np.isfinite(G["sigma_rate_mm_per_yr"])
    fit: ShrinkageFit = fit_shrinkage(G.loc[fit_mask, "rate_mm_per_yr"], G.loc[fit_mask, "sigma_rate_mm_per_yr"])
    sm, ss = fit.posterior(G["rate_mm_per_yr"], G["sigma_rate_mm_per_yr"])
    G["shrunk_rate_mm_per_yr"] = sm
    G["shrunk_sigma_mm_per_yr"] = ss

    # ---------------- forecast decision ----------------
    use_shrink = cfg.forecast_method == "shrinkage" and fit.fitted
    H = cfg.forecast_horizon_years
    thr = cfg.screening_threshold_pct_wt / 100.0
    status, reason, rate_c, rate_u, basis = [], [], [], [], []
    for r in G.itertuples():
        st, why, rc, ru = "NOT_ESTABLISHED", "", np.nan, np.nan
        b = "baseline observed rate"
        if r.match_status == "AMBIGUOUS":
            why = "Match unresolved: more than one plausible pairing. Verify the match before forecasting."
        elif r.match_status == "NEW_LATER":
            why = "Single observation (new in later run): no history, so no growth rate can be calculated."
        elif r.match_status == "UNMATCHED_EARLIER":
            why = "Not found in the later run: no second observation."
        elif r.match_status == "EXCLUDED":
            why = "Record excluded from matching (see data-quality flags)."
        elif not (r.depth_valid_a and r.depth_valid_b):
            why = "Depth missing or invalid in at least one run."
        elif r.change_class == "UNCERTAINTY_UNKNOWN":
            why = ("Measurement uncertainty unknown: the observed change cannot be distinguished from measurement noise, "
                   "so no forecast is made.")
        elif r.change_class == "DECREASE_BEYOND_NOISE":
            why = ("Observed depth decreased by more than measurement noise allows. Possible sizing difference between tools, "
                   "mis-match or data error. No forecast; verify.")
        else:
            rate = r.shrunk_rate_mm_per_yr if use_shrink else r.rate_mm_per_yr
            sig = r.shrunk_sigma_mm_per_yr if use_shrink else r.sigma_rate_mm_per_yr
            b = "empirical-Bayes shrinkage (model B)" if use_shrink else "baseline observed rate"
            ru = rate + k * sig
            if use_shrink or r.change_class == "INCREASE_BEYOND_NOISE":
                st, rc = "CENTRAL_AND_UPPER", rate
                why = (f"Constant-rate projection using the {b}; upper scenario adds {k:g} sigma of measurement noise. "
                       "Only two observations: long-term trend is NOT established.")
            else:
                st = "UPPER_ONLY"
                why = (f"Observed change is within measurement noise (|D| <= {k:g} sigma), so a central growth rate cannot "
                       "be distinguished from zero. Only an upper screening scenario is shown.")
        status.append(st); reason.append(why); rate_c.append(rc); rate_u.append(ru); basis.append(b)
    G["forecast_status"] = status
    G["forecast_status_label"] = G["forecast_status"].map(FORECAST_STATUSES)
    G["forecast_reason"] = reason
    G["forecast_basis"] = basis
    G["proj_rate_central"] = rate_c
    G["proj_rate_upper"] = rate_u
    G["horizon_years"] = H
    G["proj_depth_central_mm"] = G["depth_b"] + G["proj_rate_central"] * H
    G["proj_depth_upper_mm"] = G["depth_b"] + G["proj_rate_upper"] * H
    G["proj_pct_central"] = G["proj_depth_central_mm"] / G["wt_mm"] * 100
    G["proj_pct_upper"] = G["proj_depth_upper_mm"] / G["wt_mm"] * 100

    def years_to(depth, rate, wt):
        if not (np.isfinite(depth) and np.isfinite(wt)):
            return np.nan
        tgt = thr * wt
        if depth >= tgt:
            return 0.0
        if not np.isfinite(rate) or rate <= 0:
            return np.inf
        return (tgt - depth) / rate

    G["yrs_to_threshold_central"] = [years_to(d, r, w) for d, r, w in zip(G["depth_b"], G["proj_rate_central"], G["wt_mm"])]
    G["yrs_to_threshold_upper"] = [years_to(d, r, w) for d, r, w in zip(G["depth_b"], G["proj_rate_upper"], G["wt_mm"])]

    # ---------------- additional data-quality issues discovered after matching ----------------
    extra = []
    for r in G[G["suspicious_change"]].itertuples():
        extra.append(dict(severity="Warning", code="SUSPICIOUS_CHANGE", run_id=mr.run_b, observation_id=r.obs_b,
                          field="depth_mm", value=f"{r.rate_mm_per_yr:+.3f} mm/yr",
                          message=(f"{r.track_id}: annualised change {r.rate_mm_per_yr:+.3f} mm/yr exceeds the demo plausibility "
                                   f"limit of +/-{cfg.suspicious_rate_mm_per_yr} mm/yr ({r.obs_a} -> {r.obs_b})."),
                          effect="Kept as observed and flagged; review priority raised for verification.",
                          action="Verify the match and the sizing of both records."))
    for r in G[G["wt_conflict"]].itertuples():
        extra.append(dict(severity="Warning", code="WT_CONFLICT", run_id=mr.run_b, observation_id=r.obs_b,
                          field="nominal_wt_mm", value=f"{r.wt_a} vs {r.wt_b}",
                          message=f"{r.track_id}: nominal wall thickness differs between runs ({r.wt_a} vs {r.wt_b} mm).",
                          effect="Later-run value used; flagged.", action="Confirm the wall thickness from pipe-book records."))
    return G, fit, extra
