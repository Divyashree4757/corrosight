"""Evidence Gap Finder and Data Trust Scorecard.

Evidence gaps: what is missing or unresolved for each finding, and which single data request would unblock the
most findings. Trust scorecard: completeness / validity / consistency measures of the loaded data, reported as
separate, transparent percentages (no composite confidence score).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

GAP_TYPES = {
    "missing_input": "Missing engineering input",
    "uncertainty_unknown": "Measurement uncertainty not stated",
    "ambiguous_match": "Defect identity unresolved",
    "single_observation": "Single observation (no growth history)",
    "invalid_depth": "Depth missing or invalid",
    "excluded": "Record excluded from matching",
    "anomaly": "Unresolved measurement anomaly (High)",
}


def finding_gaps(F: pd.DataFrame, anomalies: pd.DataFrame | None = None) -> pd.DataFrame:
    rows = []
    hi = set(anomalies.loc[anomalies["severity"] == "High", "track_id"].dropna()) if anomalies is not None and len(anomalies) else set()
    for r in F.itertuples():
        def add(kind, detail, resolve):
            rows.append(dict(track_id=r.track_id, segment_id=r.segment_id, review_category=r.review_category,
                             gap_type=GAP_TYPES[kind], detail=detail, resolve_with=resolve))
        for item in [x for x in str(r.inputs_missing).split("; ") if x and x != "nan"]:
            add("missing_input", item, f"Obtain '{item}' from design / operating records")
        if r.change_class == "UNCERTAINTY_UNKNOWN":
            add("uncertainty_unknown", "Depth uncertainty missing for at least one record",
                "Tool sizing specification from the inspection vendor")
        if r.match_status == "AMBIGUOUS":
            add("ambiguous_match", f"{r.obs_a} -> {r.obs_b} has competing candidates", "Raw ILI signal comparison / reviewer resolution")
        if r.match_status in ("NEW_LATER", "UNMATCHED_EARLIER"):
            add("single_observation", r.match_status_label, "A further inspection run or a confirmed match")
        if not np.isfinite(r.latest_depth_mm):
            add("invalid_depth", "No valid depth measurement", "Vendor sizing record")
        if r.match_status == "EXCLUDED":
            add("excluded", str(r.rationale), "Resolve the record's data issue")
        if r.track_id in hi:
            add("anomaly", "High-severity measurement flag", "See Measurement Anomaly Detective")
    return pd.DataFrame(rows, columns=["track_id", "segment_id", "review_category", "gap_type", "detail", "resolve_with"])


def unlock_opportunities(F: pd.DataFrame) -> pd.DataFrame:
    """Data requests that would make the most findings readiness-complete (single missing input per finding)."""
    rows = []
    for r in F.itertuples():
        miss = [x for x in str(r.inputs_missing).split("; ") if x and x != "nan"]
        if len(miss) == 1:
            rows.append(dict(input=miss[0], segment_id=r.segment_id, track_id=r.track_id))
    if not rows:
        return pd.DataFrame(columns=["data_request", "segments", "findings_unblocked"])
    D = pd.DataFrame(rows)
    g = D.groupby("input").agg(segments=("segment_id", lambda s: ", ".join(sorted(s.dropna().unique()))),
                               findings_unblocked=("track_id", "nunique")).reset_index()
    g = g.rename(columns={"input": "data_request"}).sort_values("findings_unblocked", ascending=False)
    return g.reset_index(drop=True)


def trust_scorecard(result) -> dict:
    d = result.validation.data
    m = result.match
    sub = d[d["run_id"].isin([m.run_a, m.run_b])]
    fields = ["axial_position_m", "clock_position_h", "depth_mm", "length_mm", "width_mm", "nominal_wt_mm",
              "depth_uncertainty_mm", "outer_diameter_mm", "smys_mpa", "maop_kpa"]
    comp = []
    for run, g in sub.groupby("run_id"):
        row = {"run_id": run, "records": len(g)}
        for f in fields:
            row[f] = float(g[f].notna().mean() * 100) if f in g else 0.0
        comp.append(row)
    completeness = pd.DataFrame(comp)
    validity = []
    for run, g in sub.groupby("run_id"):
        validity.append(dict(run_id=run, location_valid=float(g["location_valid"].mean() * 100),
                             clock_valid=float(g["clock_valid"].mean() * 100), depth_valid=float(g["depth_valid"].mean() * 100),
                             wall_thickness_valid=float(g["wt_valid"].mean() * 100),
                             uncertainty_stated=float(g["uncertainty_known"].mean() * 100),
                             not_duplicate=float((g["duplicate_of"].isna()).mean() * 100)))
    validity = pd.DataFrame(validity)
    mc = m.status_counts()
    n_a = int((sub["run_id"] == m.run_a).sum())
    off = m.offsets
    consistency = pd.DataFrame([
        dict(measure="Earlier records with a likely match", value=mc["LIKELY_MATCH"] / max(n_a, 1) * 100, unit="%"),
        dict(measure="Paired findings that are ambiguous", value=mc["AMBIGUOUS"] / max(mc["LIKELY_MATCH"] + mc["AMBIGUOUS"], 1) * 100, unit="%"),
        dict(measure="Segments with their own odometer offset (>=3 anchors)",
             value=float((off["source"] == "segment median").mean() * 100) if len(off) else 0.0, unit="%"),
        dict(measure="Paired changes decreasing beyond noise",
             value=float((result.growth["change_class"] == "DECREASE_BEYOND_NOISE").sum()
                         / max(result.growth["delta_mm"].notna().sum(), 1) * 100), unit="%"),
    ])
    seg = sub.groupby("segment_id").agg(records=("observation_id", "size"),
                                        depth_valid=("depth_valid", "mean"), wt_valid=("wt_valid", "mean"),
                                        uncertainty_stated=("uncertainty_known", "mean"),
                                        flagged=("quality_flags", lambda s: (s.str.len() > 0).mean())).reset_index()
    for c in ("depth_valid", "wt_valid", "uncertainty_stated", "flagged"):
        seg[c] = seg[c] * 100
    return dict(completeness=completeness, validity=validity, consistency=consistency, segments=seg)


def band(pct: float) -> str:
    """Demo display bands for a percentage measure (not an engineering criterion)."""
    if not np.isfinite(pct):
        return "n/a"
    return "Good (>=95%)" if pct >= 95 else "Fair (80-95%)" if pct >= 80 else "Poor (<80%)"
