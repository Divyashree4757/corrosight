"""Engineering Review Readiness checker.

CorroSight does NOT perform a remaining-strength assessment (e.g. methods in the ASME B31G family),
does not compute failure pressures, safety factors or probabilities of failure, and does not claim
compliance with any standard. This module only reports whether the inputs that such an assessment
would typically need are present, and what still needs verification, so that a qualified engineer
can decide what to do next.

Four different questions are deliberately kept apart:
  1. Corrosion-growth estimation       - what CorroSight calculates (observed change, rates, scenarios)
  2. Time to a screening threshold      - CorroSight illustrative scenario vs a DEMO threshold
  3. Remaining-strength assessment      - NOT performed; requires an engineer-selected method
  4. Probability of pipeline failure    - NOT estimated
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SCOPE_TABLE = [
    ("Corrosion-growth estimation", "Calculated by CorroSight",
     "Observed change and annualised rate between two matched observations, with measurement-noise interval."),
    ("Time to a demo screening threshold", "Illustrative scenario only",
     "Constant-rate projection against a configurable demo threshold. Not a repair deadline or remaining life."),
    ("Remaining-strength assessment", "NOT performed",
     "Requires an applicable method chosen and applied by a qualified engineer, with verified inputs."),
    ("Probability of pipeline failure", "NOT estimated",
     "Would require validated models, material/operational data and engineering judgement."),
]

# inputs commonly needed by remaining-strength methods for metal loss; the exact list depends on the method
CORE_INPUTS = [
    ("latest_depth", "Defect depth (latest valid measurement)"),
    ("length", "Defect axial length"),
    ("wt", "Nominal wall thickness"),
    ("od", "Pipe outer diameter"),
    ("smys", "Pipe grade / SMYS"),
    ("maop", "Operating pressure (MAOP)"),
]

ALWAYS_VERIFY = "Tool sizing accuracy and any bias between inspection tools (always required)"

READINESS_LABELS = {
    "MISSING_INPUTS": "Not ready - inputs missing",
    "VERIFY": "Inputs present - verification required",
    "INPUTS_PRESENT": "Inputs present for an engineer-selected assessment (not performed here)",
}


def assess_readiness(G: pd.DataFrame) -> pd.DataFrame:
    """Return one row per track with available / missing / verification lists and a readiness status."""
    out = []
    for r in G.itertuples():
        have = {
            "latest_depth": np.isfinite(r.latest_depth_mm),
            "length": np.isfinite(r.length_b) if isinstance(r.obs_b, str) else np.isfinite(r.length_a),
            "wt": np.isfinite(r.wt_mm),
            "od": np.isfinite(r.od_mm) and r.od_mm > 0,
            "smys": np.isfinite(r.smys) and r.smys > 0,
            "maop": np.isfinite(r.maop) and r.maop > 0,
        }
        available = [lbl for k, lbl in CORE_INPUTS if have[k]]
        missing = [lbl for k, lbl in CORE_INPUTS if not have[k]]
        verify = []
        if r.match_status == "AMBIGUOUS":
            verify.append("Defect correspondence between runs (ambiguous match)")
        if r.match_status == "NEW_LATER":
            verify.append("Single observation only: no measured growth history")
        if r.match_status == "UNMATCHED_EARLIER":
            verify.append("Not found in later run: current condition unknown")
        if r.match_status == "EXCLUDED":
            verify.append("Record excluded from matching: resolve data issue first")
        if r.change_class == "UNCERTAINTY_UNKNOWN" or (have["latest_depth"] and not _unc_known(r)):
            verify.append("Depth measurement uncertainty (not stated)")
        if r.change_class == "DECREASE_BEYOND_NOISE":
            verify.append("Sizing consistency between tools (anomalous decrease)")
        if bool(r.suspicious_change):
            verify.append("Implausibly large observed change")
        if bool(r.wt_conflict):
            verify.append("Wall thickness differs between runs")
        if missing:
            status = "MISSING_INPUTS"
        elif verify:
            status = "VERIFY"
        else:
            status = "INPUTS_PRESENT"
        out.append(dict(track_id=r.track_id, readiness=status, readiness_label=READINESS_LABELS[status],
                        inputs_available="; ".join(available), inputs_missing="; ".join(missing),
                        requires_verification="; ".join(verify + [ALWAYS_VERIFY])))
    return pd.DataFrame(out)


def _unc_known(r) -> bool:
    if r.latest_depth_source == "none":
        return False
    u = r.u_b if isinstance(r.obs_b, str) and r.depth_valid_b else r.u_a
    return bool(np.isfinite(u))


def readiness_summary(R: pd.DataFrame) -> dict:
    counts = R["readiness"].value_counts().to_dict()
    missing = R["inputs_missing"].str.split("; ").explode()
    missing = missing[missing.astype(bool) & missing.notna()]
    return {"counts": {k: int(counts.get(k, 0)) for k in READINESS_LABELS},
            "most_common_missing": missing.value_counts().to_dict()}
