"""Measurement Anomaly Detective: explainable flags for suspicious inspection measurements.

Sources (no duplicated logic):
  * record-level checks come from the existing validation issues (src/validation.py) and the post-matching
    checks in src/prediction.py (SUSPICIOUS_CHANGE, WT_CONFLICT);
  * cross-run checks below use the existing growth table (observed change, measurement sigma).

A flag means "this measurement needs checking". It is never treated as a corrosion event, and original
values are never changed. Proposed corrections are stored separately (CorrectionLog) and are NOT applied
to the analysis.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .logstore import JsonLog


@dataclass(frozen=True)
class AnomalyConfig:
    """Demo assumptions for the cross-run checks (editable in the UI)."""
    change_z_notable: float = 3.0       # |change| / sigma above this -> large relative to measurement uncertainty
    robust_z_outlier: float = 4.0       # robust z of annualised rate vs. population (median / MAD)
    length_change_mm: float = 25.0      # |length change| above this AND above 60 % of the earlier length
    length_change_frac: float = 0.60
    deep_pct_wt: float = 80.0           # reported depth above this % of nominal WT -> verify sizing

    def to_dict(self) -> dict:
        return asdict(self)


# validation code -> (check name, rule text, severity, review category, evidence required, next step)
VALIDATION_MAP = {
    "MISSING_DEPTH": ("Missing value", "depth_mm must be present", "High", "Data correction needed",
                      "Vendor sizing record for this anomaly", "Request the depth from the inspection vendor"),
    "NON_POSITIVE_DEPTH": ("Invalid value", "depth_mm > 0", "High", "Data correction needed",
                           "Vendor listing and sign convention", "Confirm the reported depth"),
    "DEPTH_UNIT_SUSPECT": ("Possible unit mismatch", "depth_mm <= 50 mm (mm expected)", "High", "Data correction needed",
                           "Unit used in the vendor listing", "Confirm units; correct the source file"),
    "DEPTH_EXCEEDS_WT": ("Implausible dimension", "depth_mm <= nominal_wt_mm", "High", "Verify measurement",
                         "Sizing record and pipe-book wall thickness", "Verify depth and wall thickness"),
    "INVALID_WALL_THICKNESS": ("Invalid metadata", "0 < nominal_wt_mm <= 50", "High", "Data correction needed",
                               "Pipe-book / design records", "Correct the wall thickness"),
    "INVALID_POSITION": ("Invalid axial position", "0 <= axial_position_m <= pipeline length", "High", "Data correction needed",
                         "Odometer reference and girth-weld listing", "Check the odometer reference"),
    "MISSING_POSITION": ("Missing value", "axial_position_m must be present", "High", "Data correction needed",
                         "Vendor feature listing", "Request the reported position"),
    "INVALID_CLOCK": ("Invalid clock position", "0 <= clock_position_h <= 12", "Medium", "Data correction needed",
                      "Clock convention (hours vs degrees)", "Confirm the clock convention"),
    "NON_NUMERIC": ("Invalid data type", "numeric value expected", "High", "Data correction needed",
                    "Original export from the vendor", "Correct the value in the source file"),
    "EXACT_DUPLICATE": ("Duplicate record", "rows must be unique", "Medium", "Verify measurement",
                        "Vendor confirmation of a double listing", "Confirm and remove the duplicate at source"),
    "POSSIBLE_DUPLICATE": ("Possible duplicate", "near-identical record in the same run", "Medium", "Verify measurement",
                           "Raw ILI signal review for both calls", "Confirm whether this is one anomaly or two"),
    "DUPLICATE_ID": ("Duplicate identifier", "observation_id unique within run", "Medium", "Data correction needed",
                     "Vendor listing", "Resolve conflicting records"),
    "SUSPICIOUS_CHANGE": ("Unusually large change", "|annualised change| <= demo plausibility limit", "High", "Verify measurement",
                          "Sizing records of both runs and the match evidence", "Verify the match and both sizings"),
    "WT_CONFLICT": ("Conflict with metadata", "same nominal WT in both runs", "Medium", "Verify measurement",
                    "Pipe-book records", "Confirm the wall thickness"),
}


def _obs_to_track(G: pd.DataFrame) -> dict:
    m = {}
    for r in G.itertuples():
        if isinstance(r.obs_a, str):
            m.setdefault(r.obs_a, r.track_id)
        if isinstance(r.obs_b, str):
            m.setdefault(r.obs_b, r.track_id)
    return m


def detect(result, cfg: AnomalyConfig | None = None) -> pd.DataFrame:
    cfg = cfg or AnomalyConfig()
    G = result.growth
    o2t = _obs_to_track(G)
    rows = []
    # ---- record-level flags from validation / prediction issues
    for r in result.issues.itertuples():
        if r.code not in VALIDATION_MAP or not isinstance(r.observation_id, str):
            continue
        check, rule, sev, cat, ev, step = VALIDATION_MAP[r.code]
        rows.append(dict(track_id=o2t.get(r.observation_id), run_id=r.run_id, observation_id=r.observation_id,
                         check=check, code=r.code, observed=r.value if isinstance(r.value, str) and r.value else "(no value recorded)",
                         comparison=rule, reason=r.message,
                         severity=sev, review_category=cat, evidence_required=ev, next_step=step,
                         source="validation"))
    # ---- cross-run checks on paired findings
    P = G[G["match_status"].isin(["LIKELY_MATCH", "AMBIGUOUS"]) & G["delta_mm"].notna()]
    rates = G.loc[G["match_status"] == "LIKELY_MATCH", "rate_mm_per_yr"].dropna()
    med = float(rates.median()) if len(rates) else 0.0
    mad = float(np.median(np.abs(rates - med)) * 1.4826) if len(rates) else 0.0
    for r in P.itertuples():
        base = dict(track_id=r.track_id, run_id=None, observation_id=f"{r.obs_a} -> {r.obs_b}", source="cross-run")
        if np.isfinite(r.sigma_delta_mm) and r.sigma_delta_mm > 0:
            z = r.delta_mm / r.sigma_delta_mm
            if z < -2:
                rows.append(dict(base, check="Decrease beyond measurement noise", code="DECREASE_Z",
                                 observed=f"change {r.delta_mm:+.2f} mm (z = {z:.1f})", comparison="z >= -2 expected for metal loss",
                                 reason="Reported depth fell by more than measurement noise allows; metal loss does not reverse.",
                                 severity="High", review_category="Verify measurement",
                                 evidence_required="Sizing of both runs; match evidence", next_step="Verify match and sizing"))
            elif z > cfg.change_z_notable:
                rows.append(dict(base, check="Change large relative to uncertainty", code="LARGE_Z",
                                 observed=f"change {r.delta_mm:+.2f} mm (z = {z:.1f})",
                                 comparison=f"z <= {cfg.change_z_notable:g} (demo)",
                                 reason="Change is many times the stated measurement uncertainty. May be genuine growth; confirm before relying on it.",
                                 severity="Low", review_category="Context",
                                 evidence_required="Confirmation that both sizings are reliable", next_step="Confirm with source data"))
        if mad > 0 and np.isfinite(r.rate_mm_per_yr):
            rz = (r.rate_mm_per_yr - med) / mad
            if abs(rz) > cfg.robust_z_outlier:
                rows.append(dict(base, check="Unusual rate vs. population", code="RATE_OUTLIER",
                                 observed=f"{r.rate_mm_per_yr:+.3f} mm/yr (robust z = {rz:.1f})",
                                 comparison=f"|robust z| <= {cfg.robust_z_outlier:g}; median {med:.3f}, MAD-sigma {mad:.3f}",
                                 reason="Annualised change is far from the rest of the line's observed rates.",
                                 severity="Medium", review_category="Verify measurement",
                                 evidence_required="Both sizings; local context", next_step="Verify before using in planning"))
        if np.isfinite(r.length_a) and np.isfinite(r.length_b):
            dl = r.length_b - r.length_a
            if abs(dl) > cfg.length_change_mm and abs(dl) > cfg.length_change_frac * max(r.length_a, 1):
                rows.append(dict(base, check="Dimension inconsistency between runs", code="LENGTH_CHANGE",
                                 observed=f"length {r.length_a:.0f} -> {r.length_b:.0f} mm",
                                 comparison=f"|change| <= {cfg.length_change_mm:g} mm or <= {cfg.length_change_frac:.0%}",
                                 reason="Reported length changed strongly; possible mis-match, coalescing anomalies or sizing difference.",
                                 severity="Medium", review_category="Verify measurement",
                                 evidence_required="Raw signal review of both calls", next_step="Check the match and box sizing"))
    for r in G[np.isfinite(G["latest_pct_wt"]) & (G["latest_pct_wt"] >= cfg.deep_pct_wt)].itertuples():
        rows.append(dict(track_id=r.track_id, run_id=r.latest_depth_source, observation_id=r.obs_b if r.depth_valid_b else r.obs_a,
                         check="Unusually deep relative to metadata", code="DEEP_PCT",
                         observed=f"{r.latest_depth_mm:.2f} mm = {r.latest_pct_wt:.0f}% of nominal WT",
                         comparison=f"< {cfg.deep_pct_wt:g}% WT (demo)", source="cross-run",
                         reason="Reported depth is a large share of nominal wall thickness; sizing and WT should be confirmed.",
                         severity="High", review_category="Verify measurement",
                         evidence_required="Sizing record; pipe-book WT", next_step="Verify sizing and wall thickness"))
    cols = ["flag_id", "track_id", "run_id", "observation_id", "check", "code", "observed", "comparison", "reason",
            "severity", "review_category", "evidence_required", "next_step", "source"]
    A = pd.DataFrame(rows)
    if A.empty:
        return pd.DataFrame(columns=cols)
    sev = {"High": 0, "Medium": 1, "Low": 2}
    A = A.sort_values(["severity", "track_id"], key=lambda s: s.map(sev) if s.name == "severity" else s.fillna("~"))
    A.insert(0, "flag_id", [f"A{i + 1:03d}" for i in range(len(A))])
    return A[cols].reset_index(drop=True)


class CorrectionLog(JsonLog):
    """Proposed measurement corrections. Stored separately; the analysis keeps using the original values."""

    def propose(self, dataset_fp: str, run_id: str, observation_id: str, field: str, original_value, proposed_value,
                rationale: str, reviewer: str, flag_id: str = "", actor: dict | None = None) -> dict:
        if not rationale.strip():
            raise ValueError("A correction proposal needs a rationale.")
        return self.append(dict(dataset_fingerprint=dataset_fp, run_id=run_id, observation_id=observation_id,
                                field=field, original_value=original_value, proposed_value=proposed_value,
                                rationale=rationale.strip(), reviewer=reviewer.strip() or "(not given)", flag_id=flag_id,
                                user_id=(actor or {}).get("user_id", ""), user_role=(actor or {}).get("role", ""),
                                status="Proposed - NOT applied to the analysis"))
