"""Contradiction Finder: explicit rules that surface findings whose evidence points in different directions.

Each contradiction lists the evidence on both sides, why they conflict, and what would resolve it. Findings are
NOT collapsed into a single confidence score, and nothing here decides whether a pipeline is safe.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RULES = {
    "K1": "High condition indicators rest on an ambiguous match",
    "K2": "Large calculated change, but a source record has data-quality flags",
    "K3": "Conclusion depends on the assumed growth rate",
    "K4": "Priority hinges on a measurement within its own uncertainty of the threshold",
    "K5": "Measured depth decreased, contradicting irreversible metal loss",
    "K6": "Deep defect with no earlier record",
    "K7": "Reviewer decisions disagree",
    "K8": "Reviewer identity resolution disagrees with the algorithm",
}


def _flags(r) -> str:
    f = "; ".join(x for x in (r.flags_a, r.flags_b) if isinstance(x, str) and x)
    return f


def find(result, reviews_history: list[dict] | None = None, resolutions: dict | None = None) -> pd.DataFrame:
    F = result.findings
    cfg = result.config
    k = cfg.noise_k
    out = []

    def add(r, rule, side_a, side_b, why, resolve):
        out.append(dict(track_id=r.track_id, rule=rule, title=RULES[rule], review_category=r.review_category,
                        evidence_a=side_a, evidence_b=side_b, conflict=why, resolve_with=resolve))

    for r in F.itertuples():
        if r.condition_level == "High" and r.match_status == "AMBIGUOUS":
            add(r, "K1", f"Condition: {r.condition_reasons.split(' | ')[0]}",
                f"Identity: ambiguous pairing {r.obs_a} -> {r.obs_b}; alternatives {r.alternatives}",
                "The concerning value may belong to a different physical defect.",
                "Defect Identity Conflict review; raw ILI signal comparison")
        fl = _flags(r)
        quality = [x for x in fl.split("; ") if x and x not in ("MISSING_UNCERTAINTY", "MISSING_WALL_THICKNESS")]
        if (r.change_class == "INCREASE_BEYOND_NOISE" or bool(r.suspicious_change)) and quality:
            add(r, "K2", f"Calculated change {r.delta_mm:+.2f} mm ({r.rate_mm_per_yr:+.3f} mm/yr)",
                f"Data-quality flags on source records: {', '.join(sorted(set(quality)))}",
                "The growth figure relies on records that validation questioned.",
                "Confirm the flagged records with the inspection vendor")
        if r.forecast_status != "NOT_ESTABLISHED" and np.isfinite(r.yrs_to_threshold_upper):
            up_hit = r.yrs_to_threshold_upper <= cfg.forecast_horizon_years
            c_hit = np.isfinite(r.yrs_to_threshold_central) and r.yrs_to_threshold_central <= cfg.forecast_horizon_years
            if up_hit and not c_hit:
                cen = ("central projection not established" if r.forecast_status == "UPPER_ONLY"
                       else f"central scenario: {r.yrs_to_threshold_central:.1f} yr" if np.isfinite(r.yrs_to_threshold_central)
                       else "central scenario does not reach it")
                add(r, "K3", f"Upper scenario reaches the demo {cfg.screening_threshold_pct_wt:g}% WT threshold in "
                             f"{r.yrs_to_threshold_upper:.1f} yr", cen,
                    "Whether the threshold is reached within the horizon depends on which growth rate is assumed.",
                    "A further inspection (third data point) or tighter sizing uncertainty")
        if np.isfinite(r.latest_pct_wt) and np.isfinite(r.wt_mm):
            u = r.u_b if r.depth_valid_b else r.u_a
            if np.isfinite(u) and u > 0:
                thr = cfg.depth_review_pct_wt / 100 * r.wt_mm
                lo, hi = r.latest_depth_mm - k * u, r.latest_depth_mm + k * u
                if lo < thr <= hi:
                    side = "triggers" if r.latest_depth_mm >= thr else "does not trigger"
                    add(r, "K4", f"Latest depth {r.latest_depth_mm:.2f} mm {side} the demo {cfg.depth_review_pct_wt:g}% WT rule "
                                 f"({thr:.2f} mm)",
                        f"Measurement range +/-{k:g} sigma: {lo:.2f} to {hi:.2f} mm spans the threshold",
                        "The depth-based priority could flip within measurement uncertainty.",
                        "Higher-accuracy sizing (e.g. field verification) of this anomaly")
        if r.change_class == "DECREASE_BEYOND_NOISE":
            add(r, "K5", f"{r.obs_a}: {r.depth_a:.2f} mm (earlier)", f"{r.obs_b}: {r.depth_b:.2f} mm (later)",
                f"Depth fell {r.delta_mm:+.2f} mm, beyond {k:g}-sigma noise ({r.sigma_delta_mm:.2f} mm); metal loss does not reverse.",
                "Check the match, tool-to-tool sizing bias, and whether the anomaly was repaired")
        if r.match_status == "NEW_LATER" and np.isfinite(r.latest_pct_wt) and r.latest_pct_wt >= 25:
            add(r, "K6", f"{r.obs_b}: {r.latest_depth_mm:.2f} mm = {r.latest_pct_wt:.0f}% WT in the later run",
                "No earlier record within the matching gate",
                "A defect this deep would usually have been reportable earlier unless it grew fast.",
                "Earlier-run raw data near this location; check for a missed or mis-located call")
    # reviewer disagreements
    by_track: dict[str, list[dict]] = {}
    for e in reviews_history or []:
        by_track.setdefault(e["track_id"], []).append(e)
    Fi = F.set_index("track_id")
    for tid, ents in by_track.items():
        if tid not in Fi.index:
            continue
        reviewers = {e.get("reviewer") for e in ents}
        statuses = {e.get("status") for e in ents}
        steps = {e.get("reviewer_selected_next_step") for e in ents}
        r = Fi.loc[tid]
        rr = type("R", (), dict(track_id=tid, review_category=r["review_category"]))
        if len(reviewers) > 1 and (len(statuses) > 1 or len(steps) > 1):
            add(rr, "K7", "; ".join(f"{e['reviewer']}: {e['status']}" for e in ents[-3:]),
                "; ".join(sorted(s for s in steps if s)),
                "Different reviewers recorded different statuses or next steps.",
                "Reviewer discussion; record a documented rationale")
    for tid, res in (resolutions or {}).items():
        if tid in Fi.index and res.get("resolution") != "Confirm algorithm pairing":
            r = Fi.loc[tid]
            rr = type("R", (), dict(track_id=tid, review_category=r["review_category"]))
            add(rr, "K8", f"Algorithm: {res.get('algorithm_pairing')} ({res.get('algorithm_status')})",
                f"Reviewer ({res.get('reviewer')}): {res.get('resolution')} {res.get('alternative', '')}".strip(),
                "Growth and priority are still computed from the algorithm pairing.",
                "Confirm with raw data; if the reviewer is right, the growth figures for this finding do not apply")
    cols = ["track_id", "rule", "title", "review_category", "evidence_a", "evidence_b", "conflict", "resolve_with"]
    return pd.DataFrame(out, columns=cols)
