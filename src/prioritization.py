"""Why-Inspect-First engine: transparent, rule-based review prioritisation.

Output is a REVIEW-PRIORITY RECOMMENDATION for human reviewers. It is not a risk score, a failure
probability or a repair decision. All numeric thresholds come from `AnalysisConfig` and are DEMO
ASSUMPTIONS that a qualified user can change.

Two independent axes are evaluated and shown separately:

Condition indicators (what the measurements suggest)
  C1  Latest depth >= depth_review_pct_wt % of nominal WT                          -> High
  C2  Upper screening scenario reaches screening_threshold_pct_wt within the horizon -> High
  C3  Increase beyond measurement noise AND rate >= rate_review_mm_per_yr          -> High
  C4  Increase beyond measurement noise, below the rate threshold                  -> Elevated
  C5  New detection (no history) with latest depth >= 25 % WT                      -> Elevated

Evidence quality / completeness (how far the evidence can be trusted)
  E1  Ambiguous match                                   -> Verify match / data
  E2  Decrease beyond measurement noise                 -> Verify match / data
  E3  Implausibly large observed change                 -> Verify match / data
  E4  Previously reported anomaly (>= 25 % WT) not found in later run -> Verify match / data
  E5  Possible duplicate excluded from matching         -> Verify match / data
  E6  Wall thickness conflict between runs              -> Verify match / data
  E7  Depth missing / invalid; location invalid         -> Additional data needed
  E8  Nominal wall thickness missing                    -> Additional data needed
  E9  Depth measurement uncertainty missing             -> Additional data needed
  E10 Single observation (new detection)                -> noted (limits evidence, no category change)

Review category = the HIGHEST of the condition-based and evidence-based categories:
  1 Review first  >  2 Verify match / data  >  3 Additional data needed  >  4 Monitor  >  5 Routine review
Because the higher category always wins, missing or uncertain evidence can only RAISE a finding,
never lower it. Within a category, findings are ordered by the larger of latest % WT and upper-scenario
% WT (unknown % WT is listed first, so it is not hidden), then by observed rate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import AnalysisConfig

CATEGORIES = {
    1: "Review first",
    2: "Verify match / data",
    3: "Additional data needed",
    4: "Monitor",
    5: "Routine review",
}

NEXT_STEPS = {
    1: "Send for engineering review",
    2: "Verify the defect match / sizing against source ILI data",
    3: "Request missing inputs",
    4: "Include in next scheduled data review",
    5: "Routine review; no additional action proposed",
}

NEXT_STEP_OPTIONS = [
    "Send for engineering review",
    "Verify the defect match / sizing against source ILI data",
    "Request missing inputs",
    "Request additional inspection data",
    "Perform a more detailed assessment (engineer-selected method)",
    "Include in next scheduled data review",
    "Routine review; no additional action proposed",
]


def _fmt(x, nd=2, unit=""):
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{nd}f}{unit}"


def prioritize(G: pd.DataFrame, config: AnalysisConfig | None = None, run_a: str = "", run_b: str = "") -> pd.DataFrame:
    cfg = config or AnalysisConfig()
    H = cfg.forecast_horizon_years
    rows = []
    for r in G.itertuples():
        cond, cond_lvl = [], []
        ev, ev_cat = [], []
        missing_inputs = []
        src = r.obs_b if r.latest_depth_source == run_b else r.obs_a
        pct = r.latest_pct_wt

        # ---------------- condition ----------------
        if np.isfinite(pct) and pct >= cfg.depth_review_pct_wt:
            cond.append(f"C1: latest depth {_fmt(r.latest_depth_mm)} mm = {pct:.0f}% of nominal WT {_fmt(r.wt_mm, 1)} mm "
                        f"({src}, {r.latest_depth_source}) >= demo threshold {cfg.depth_review_pct_wt:.0f}%.")
            cond_lvl.append(1)
        if np.isfinite(r.yrs_to_threshold_upper) and r.yrs_to_threshold_upper <= H and r.forecast_status != "NOT_ESTABLISHED":
            cond.append(f"C2: upper screening scenario ({_fmt(r.proj_rate_upper, 3)} mm/yr) reaches the demo "
                        f"{cfg.screening_threshold_pct_wt:.0f}% WT threshold in {_fmt(r.yrs_to_threshold_upper, 1)} yr "
                        f"(<= {H:g}-yr horizon). Illustrative, not a deadline.")
            cond_lvl.append(1)
        if r.change_class == "INCREASE_BEYOND_NOISE":
            txt = (f"observed change {r.delta_mm:+.2f} mm over {r.dt_years:.1f} yr = {r.rate_mm_per_yr:+.3f} mm/yr "
                   f"({r.obs_a} -> {r.obs_b}) exceeds {cfg.noise_k:g} sigma noise ({_fmt(r.sigma_delta_mm)} mm)")
            if r.rate_mm_per_yr >= cfg.rate_review_mm_per_yr:
                cond.append(f"C3: {txt} and >= demo rate {cfg.rate_review_mm_per_yr} mm/yr.")
                cond_lvl.append(1)
            else:
                cond.append(f"C4: {txt}; below demo rate {cfg.rate_review_mm_per_yr} mm/yr.")
                cond_lvl.append(4)
        if r.match_status == "NEW_LATER" and np.isfinite(pct) and 25 <= pct < cfg.depth_review_pct_wt:
            cond.append(f"C5: new detection {r.obs_b} at {pct:.0f}% WT with no earlier history.")
            cond_lvl.append(4)

        if not np.isfinite(r.latest_depth_mm):
            cond_level = "Not assessable"
        elif 1 in cond_lvl:
            cond_level = "High"
        elif 4 in cond_lvl:
            cond_level = "Elevated"
        else:
            cond_level = "No rule triggered"

        # ---------------- evidence ----------------
        if r.match_status == "AMBIGUOUS":
            ev.append(f"E1: ambiguous match {r.obs_a} -> {r.obs_b}; alternatives: {r.alternatives}.")
            ev_cat.append(2)
        if r.change_class == "DECREASE_BEYOND_NOISE":
            ev.append(f"E2: depth decreased {r.delta_mm:+.2f} mm, beyond {cfg.noise_k:g} sigma noise "
                      f"({_fmt(r.sigma_delta_mm)} mm): possible sizing difference or mis-match.")
            ev_cat.append(2)
        if bool(r.suspicious_change):
            ev.append(f"E3: implausibly large change {r.rate_mm_per_yr:+.3f} mm/yr "
                      f"(> {cfg.suspicious_rate_mm_per_yr} mm/yr demo plausibility limit).")
            ev_cat.append(2)
        if r.match_status == "UNMATCHED_EARLIER":
            p_a = r.depth_a / r.wt_mm * 100 if np.isfinite(r.wt_mm) and r.depth_valid_a else np.nan
            if not np.isfinite(p_a) or p_a >= 25:
                ev.append(f"E4: {r.obs_a} ({_fmt(r.depth_a)} mm, {_fmt(p_a, 0)}% WT in {run_a}) was not found in {run_b}; "
                          "current condition unknown.")
                ev_cat.append(2)
            else:
                ev.append(f"E4 (minor): {r.obs_a} ({p_a:.0f}% WT in {run_a}) not found in {run_b}.")
        if r.match_status == "EXCLUDED":
            if "duplicate" in str(r.rationale):
                ev.append(f"E5: {r.rationale}")
                ev_cat.append(2)
            else:
                ev.append(f"E7: {r.rationale}")
                ev_cat.append(3)
                missing_inputs.append("valid location / identifier")
        if bool(r.wt_conflict):
            ev.append(f"E6: nominal WT differs between runs ({r.wt_a} vs {r.wt_b} mm).")
            ev_cat.append(2)
        if not np.isfinite(r.latest_depth_mm) and r.match_status != "EXCLUDED":
            ev.append("E7: no valid depth measurement for this finding.")
            ev_cat.append(3)
            missing_inputs.append("valid depth")
        elif r.match_status in ("LIKELY_MATCH", "AMBIGUOUS") and not (r.depth_valid_a and r.depth_valid_b):
            ev.append("E7: depth invalid or missing in one run; change cannot be calculated.")
            ev_cat.append(3)
            missing_inputs.append("valid depth in both runs")
        if not np.isfinite(r.wt_mm):
            ev.append("E8: nominal wall thickness missing; % WT and threshold scenarios cannot be computed.")
            ev_cat.append(3)
            missing_inputs.append("nominal wall thickness")
        if r.change_class == "UNCERTAINTY_UNKNOWN":
            ev.append("E9: depth measurement uncertainty not stated; change cannot be tested against noise.")
            ev_cat.append(3)
            missing_inputs.append("depth measurement uncertainty")
        if r.match_status == "NEW_LATER":
            ev.append("E10: single observation; no growth history.")

        if not np.isfinite(r.latest_depth_mm) or r.match_status == "EXCLUDED":
            ev_level = "Insufficient"
        elif ev_cat or r.match_status in ("NEW_LATER", "UNMATCHED_EARLIER"):
            ev_level = "Limited"
        else:
            ev_level = "Adequate"

        cand = [5] + [c for c in cond_lvl] + ev_cat
        rank = min(cand)
        reasons = cond + ev
        if not reasons:
            reasons = [f"No demo review rule triggered: latest depth {_fmt(pct, 0)}% WT, change class "
                       f"'{r.change_class_label}'."]
        step = NEXT_STEPS[rank]
        if rank == 3 and missing_inputs:
            step = "Request missing inputs: " + ", ".join(dict.fromkeys(missing_inputs))
        sort_pct = np.nanmax([pct if np.isfinite(pct) else np.nan,
                              r.proj_pct_upper if np.isfinite(r.proj_pct_upper) else np.nan]) \
            if (np.isfinite(pct) or np.isfinite(r.proj_pct_upper)) else np.nan
        rows.append(dict(track_id=r.track_id, review_rank=rank, review_category=CATEGORIES[rank],
                         condition_level=cond_level, evidence_quality=ev_level,
                         condition_reasons=" | ".join(cond) if cond else "None triggered",
                         evidence_reasons=" | ".join(ev) if ev else "No evidence issue detected",
                         priority_explanation=" | ".join(reasons),
                         missing_inputs=", ".join(dict.fromkeys(missing_inputs)),
                         proposed_next_step=step, sort_pct=sort_pct))
    P = pd.DataFrame(rows)
    P["_unknown"] = ~np.isfinite(P["sort_pct"])
    rate = G.set_index("track_id")["rate_mm_per_yr"]
    P["_rate"] = P["track_id"].map(rate).fillna(-np.inf)
    P = P.sort_values(["review_rank", "_unknown", "sort_pct", "_rate"], ascending=[True, False, False, False])
    P["priority_order"] = np.arange(1, len(P) + 1)
    return P.drop(columns=["_unknown", "_rate"]).reset_index(drop=True)
