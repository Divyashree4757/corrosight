"""Corrosion Event Timeline for one finding.

Provenance of every event is explicit:
  * "Source record"        - an inspection observation in the uploaded / demo data (dated by its run date);
  * "Derived by analysis"  - matching, data-quality checks, growth, forecast and priority computed by the current
                             analysis (stamped with the analysis time; these are reconstructed from records, not
                             historical events);
  * "Recorded log"         - human reviews, identity resolutions, correction proposals, snapshots and exports
                             that the application actually logged, with their stored timestamps.
Forecast and priority REVISIONS are shown only where saved snapshots show a change; otherwise none are claimed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def build(result, track_id: str, reviews: list[dict], resolutions: list[dict], corrections: list[dict],
          snapshots: list[dict], exports: list[dict], anomalies: pd.DataFrame | None = None) -> pd.DataFrame:
    F = result.findings.set_index("track_id")
    if track_id not in F.index:
        return pd.DataFrame()
    g = F.loc[track_id]
    m = result.match
    d = result.validation.data
    ev = []

    def add(when, sort_key, etype, prov, source, values, text):
        ev.append(dict(when=when, _k=sort_key, event=etype, provenance=prov, evidence_source=source, values=values,
                       explanation=text))

    for run, obs, date in ((m.run_a, g["obs_a"], m.date_a), (m.run_b, g["obs_b"], m.date_b)):
        if isinstance(obs, str):
            rec = d[(d["run_id"] == run) & (d["observation_id"] == obs)]
            line = int(rec["source_row"].iloc[0]) if len(rec) else None
            dep = rec["depth_mm"].iloc[0] if len(rec) else np.nan
            add(f"{date:%Y-%m-%d}", f"0-{date:%Y-%m-%d}", "Inspection observation", "Source record",
                f"{run} / {obs} (CSV line {line})",
                f"depth {dep if np.isfinite(dep) else 'n/a'} mm, position {rec['axial_position_m'].iloc[0] if len(rec) else 'n/a'} m",
                "Recorded by the inspection run.")
    t0 = result.created_utc
    if anomalies is not None and len(anomalies):
        for r in anomalies[anomalies["track_id"] == track_id].itertuples():
            add(t0, f"1-{t0}-a", "Data-quality / anomaly flag", "Derived by analysis", f"{r.source}: {r.observation_id}",
                f"{r.observed} (rule: {r.comparison})", f"{r.check} - {r.severity}")
    add(t0, f"1-{t0}-b", "Proposed defect match", "Derived by analysis", "Matching (Corrosion Memory Graph)",
        f"{g['match_status_label']}" + (f", d={g['distance']:.2f}" if np.isfinite(g["distance"]) else ""), g["rationale"])
    if np.isfinite(g["delta_mm"]):
        add(t0, f"1-{t0}-c", "Growth calculation", "Derived by analysis", "Observed change",
            f"{g['delta_mm']:+.2f} mm over {g['dt_years']:.2f} yr = {g['rate_mm_per_yr']:+.3f} mm/yr",
            g["change_class_label"])
    add(t0, f"1-{t0}-d", "Forecast status", "Derived by analysis", f"Forecast ({g['forecast_basis']})",
        g["forecast_status_label"], g["forecast_reason"])
    add(t0, f"1-{t0}-e", "Review priority", "Derived by analysis", "Why-Inspect-First rules", g["review_category"],
        str(g["priority_explanation"]).split(" | ")[0])
    prev = None
    for s in snapshots:
        cur = s.get("findings", {}).get(track_id)
        if cur is None:
            continue
        txt = f"category {cur[0]}, rate {cur[1]}, forecast {cur[3]}"
        if prev is not None and prev != cur:
            changes = []
            if prev[0] != cur[0]:
                changes.append(f"priority {prev[0]} -> {cur[0]}")
            if prev[3] != cur[3] or prev[4] != cur[4]:
                changes.append("forecast revised")
            if prev[1] != cur[1]:
                changes.append(f"rate {prev[1]} -> {cur[1]}")
            add(s["timestamp_utc"], f"2-{s['timestamp_utc']}", "Revision between snapshots", "Recorded log",
                s["snapshot_id"], "; ".join(changes) or "changed", "Difference from the previous snapshot.")
        add(s["timestamp_utc"], f"2-{s['timestamp_utc']}-s", "Analysis snapshot", "Recorded log", s["snapshot_id"], txt,
            s.get("note") or "Snapshot saved.")
        prev = cur
    for e in reviews:
        if e["track_id"] == track_id:
            add(e["timestamp_utc"], f"2-{e['timestamp_utc']}", "Human review" + (" (reopened)" if e.get("action") == "reopened" else ""),
                "Recorded log", f"Reviewer: {e['reviewer']}", e["status"],
                f"Next step: {e.get('reviewer_selected_next_step', '')}. {e.get('reason') or e.get('notes') or ''}".strip())
    for e in resolutions:
        if e["track_id"] == track_id:
            add(e["timestamp_utc"], f"2-{e['timestamp_utc']}", "Identity resolution proposed", "Recorded log",
                f"Reviewer: {e['reviewer']}", f"{e['resolution']} {e.get('alternative', '')}".strip(), e["rationale"])
    obs_ids = {g["obs_a"], g["obs_b"]}
    for e in corrections:
        if e["observation_id"] in obs_ids:
            add(e["timestamp_utc"], f"2-{e['timestamp_utc']}", "Correction proposed (not applied)", "Recorded log",
                f"{e['run_id']} / {e['observation_id']}", f"{e['field']}: {e['original_value']} -> {e['proposed_value']}",
                e["rationale"])
    for e in exports:
        if e.get("tracks") == "all" or track_id in (e.get("tracks") or []):
            add(e["timestamp_utc"], f"2-{e['timestamp_utc']}", f"Exported in {e['kind']}", "Recorded log",
                e.get("file", ""), e.get("snapshot_id", "") or "-", "Evidence Passport export.")
    T = pd.DataFrame(ev).sort_values("_k", kind="stable").drop(columns=["_k"]).reset_index(drop=True)
    return T
