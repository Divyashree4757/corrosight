"""Defect Identity Conflict Detector.

Reads the candidate pairs that src/matching.py already evaluated (no re-implementation of matching) and explains,
for every candidate, what supports and what opposes it. A reviewer may record a proposed resolution, which is
stored separately: the algorithm's original pairing is never overwritten.

The normalised distance and the agreement index are similarity measures, not calibrated probabilities.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .logstore import JsonLog
from .schema import AnalysisConfig

RESOLUTION_OPTIONS = [
    "Confirm algorithm pairing",
    "Pair with an alternative candidate",
    "Treat as separate defects (no match)",
    "Unresolved - raw ILI signal review required",
]


def _candidate_reasons(c, cfg: AnalysisConfig, assigned_elsewhere: str | None, depth_note: str | None):
    sup, opp = [], []
    dx = abs(c["d_pos_aligned_m"])
    if dx <= cfg.pos_scale_m:
        sup.append(f"aligned axial difference {c['d_pos_aligned_m']:+.2f} m is within {cfg.pos_scale_m} m")
    elif dx > 2 * cfg.pos_scale_m:
        opp.append(f"aligned axial difference {c['d_pos_aligned_m']:+.2f} m exceeds {2 * cfg.pos_scale_m:.2f} m")
    if np.isfinite(c["d_clock_h"]):
        if c["d_clock_h"] <= cfg.clock_scale_h:
            sup.append(f"clock difference {c['d_clock_h']:.2f} h is within {cfg.clock_scale_h} h")
        elif c["d_clock_h"] > 1.5 * cfg.clock_scale_h:
            opp.append(f"clock difference {c['d_clock_h']:.2f} h is large")
    else:
        opp.append("clock position unavailable for at least one record")
    if np.isfinite(c["d_length_mm"]):
        if abs(c["d_length_mm"]) <= cfg.length_scale_mm:
            sup.append(f"length difference {c['d_length_mm']:+.0f} mm is within {cfg.length_scale_mm:g} mm")
        elif abs(c["d_length_mm"]) > 1.5 * cfg.length_scale_mm:
            opp.append(f"length difference {c['d_length_mm']:+.0f} mm is large")
    if abs(c["offset_m"]) > 0:
        sup.append(f"odometer offset {c['offset_m']:+.2f} m applied before comparison")
    if assigned_elsewhere:
        opp.append(f"competing claim: this candidate is assigned to {assigned_elsewhere}")
    if depth_note:
        opp.append(depth_note)
    return sup, opp


def candidate_table(result, track_id: str) -> pd.DataFrame:
    """Every candidate pair involving the finding's earlier or later record, with supporting/opposing reasons."""
    G = result.growth.set_index("track_id")
    if track_id not in G.index:
        return pd.DataFrame()
    g = G.loc[track_id]
    C = result.match.candidates
    if C is None or C.empty:
        return pd.DataFrame()
    sub = C[(C["obs_a"] == g["obs_a"]) | (C["obs_b"] == g["obs_b"])].copy()
    if sub.empty:
        return pd.DataFrame()
    assigned = C[C["assigned"]]
    a_of_b = dict(zip(assigned["obs_b"], assigned["obs_a"]))
    b_of_a = dict(zip(assigned["obs_a"], assigned["obs_b"]))
    vd = result.validation.data.drop_duplicates(subset=["run_id", "observation_id"], keep="first")
    keys = list(zip(vd["run_id"], vd["observation_id"]))
    depth = dict(zip(keys, vd["depth_mm"]))
    unc = dict(zip(keys, vd["depth_uncertainty_mm"]))
    rows = []
    best = sub["distance"].min()
    cfg = result.config
    for _, c in sub.iterrows():
        elsewhere = None
        if not c["assigned"]:
            if c["obs_b"] in a_of_b and a_of_b[c["obs_b"]] != c["obs_a"]:
                elsewhere = f"earlier record {a_of_b[c['obs_b']]}"
            elif c["obs_a"] in b_of_a and b_of_a[c["obs_a"]] != c["obs_b"]:
                elsewhere = f"later record {b_of_a[c['obs_a']]}"
        note = None
        da, db = depth.get((result.match.run_a, c["obs_a"]), np.nan), depth.get((result.match.run_b, c["obs_b"]), np.nan)
        ua, ub = unc.get((result.match.run_a, c["obs_a"]), np.nan), unc.get((result.match.run_b, c["obs_b"]), np.nan)
        if np.isfinite(da) and np.isfinite(db) and np.isfinite(ua) and np.isfinite(ub):
            if db - da < -2 * np.sqrt(ua ** 2 + ub ** 2):
                note = f"depth would decrease {db - da:+.2f} mm, beyond 2-sigma noise (depth is not used for matching)"
        sup, opp = _candidate_reasons(c, cfg, elsewhere, note)
        if c["distance"] == best:
            sup.insert(0, "lowest normalised distance among these candidates")
        rows.append(dict(earlier=c["obs_a"], later=c["obs_b"], algorithm_assigned=bool(c["assigned"]),
                         raw_dx_m=c["d_pos_raw_m"], offset_m=c["offset_m"], aligned_dx_m=c["d_pos_aligned_m"],
                         d_clock_h=c["d_clock_h"], d_length_mm=c["d_length_mm"], distance=c["distance"],
                         agreement_index=float(np.exp(-c["cost"] / 2)), competing_claim=elsewhere or "",
                         supports="; ".join(sup) or "-", opposes="; ".join(opp) or "-"))
    return pd.DataFrame(rows).sort_values("distance").reset_index(drop=True)


def conflict_overview(result) -> pd.DataFrame:
    """One row per finding with identity uncertainty: ambiguous, unmatched with candidates, or competing claims."""
    G = result.growth
    C = result.match.candidates
    rows = []
    for r in G.itertuples():
        if r.match_status == "EXCLUDED":
            continue
        n_alt = int(r.n_alternatives) if pd.notna(r.n_alternatives) else 0
        conflicting = False
        if C is not None and len(C) and n_alt:
            sub = C[((C["obs_a"] == r.obs_a) | (C["obs_b"] == r.obs_b)) & ~C["assigned"]]
            conflicting = bool(len(sub))
        kind = {"AMBIGUOUS": "Ambiguous", "LIKELY_MATCH": "Likely", "UNMATCHED_EARLIER": "Unmatched",
                "NEW_LATER": "Unmatched"}[r.match_status]
        if r.match_status == "LIKELY_MATCH" and not conflicting:
            continue
        rows.append(dict(track_id=r.track_id, group=kind, conflicting_candidates=conflicting, match_status=r.match_status_label,
                         earlier=r.obs_a, later=r.obs_b, n_candidates=n_alt, distance=r.distance,
                         margin=r.margin if pd.notna(r.margin) else np.nan, segment=r.segment_id))
    return pd.DataFrame(rows)


class ResolutionLog(JsonLog):
    def propose(self, dataset_fp: str, track_id: str, algorithm_pairing: str, algorithm_status: str,
                resolution: str, alternative: str, rationale: str, reviewer: str, actor: dict | None = None) -> dict:
        if resolution not in RESOLUTION_OPTIONS:
            raise ValueError("Unknown resolution")
        if not rationale.strip():
            raise ValueError("A resolution needs a rationale.")
        return self.append(dict(dataset_fingerprint=dataset_fp, track_id=track_id, algorithm_pairing=algorithm_pairing,
                                algorithm_status=algorithm_status, resolution=resolution, alternative=alternative,
                                rationale=rationale.strip(), reviewer=reviewer.strip() or "(not given)",
                                user_id=(actor or {}).get("user_id", ""), user_role=(actor or {}).get("role", ""),
                                note="Reviewer proposal; the algorithm's matching result is unchanged."))
