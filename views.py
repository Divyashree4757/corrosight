"""Extended CorroSight pages (v1.0): health map, timeline, identity conflicts, anomalies, patterns, what-if, model arena,
contradictions, strategy simulator, review workbench, evidence gaps, data trust, assistant, snapshots, passport & audit.

Every page reads the same AnalysisResult and the shared derived evidence in ui_core, so a finding shows the same
values everywhere. Logic lives in src/; this module only presents it.
"""

from __future__ import annotations

import json
from html import escape

import numpy as np
import pandas as pd
import streamlit as st

import ui_core as U
from src import actions as ACT
from src import charts
from src import rbac
from src import assistant as A_
from src import patterns as P_
from src import snapshots as S_
from src import strategy as ST_
from src import timeline as TL_
from src.anomalies import AnomalyConfig
from src.conflicts import RESOLUTION_OPTIONS, candidate_table, conflict_overview
from src.contradictions import RULES
from src.gaps import band, trust_scorecard, unlock_opportunities
from src.model_arena import METHODS, STRENGTHS
from src.pipeline import SourceInfo, run_analysis
from src.prioritization import CATEGORIES
from src.review import CLOSED_STATUS, WORKBENCH_STATUSES
from src.validation import read_csv

DEMO_NOTE = "Synthetic demo data: patterns and scores describe a fictional pipeline."


def _need(res) -> bool:
    if not res.ok:
        st.warning("Load valid data with two inspection runs first (see Pipeline Overview for blocking issues).")
        return False
    return True


def _track_rows(F: pd.DataFrame, ids: list[str], n: int = 10, reviews: dict | None = None):
    rv = reviews or {}
    st.markdown("".join(U.priority_row(r, rv, st.session_state.get("focus_track"))
                        for r in F[F["track_id"].isin(ids)].sort_values("priority_order").head(n).itertuples()),
                unsafe_allow_html=True)


# ============================================================================ OVERVIEW
def page_health_map(res):
    U.header(res, "Pipeline Health Map",
             "Segment-by-segment view of findings, review load, data quality and evidence gaps. "
             "Here 'health' means the state of the evidence and the review workload, not structural integrity.")
    if not _need(res):
        return
    F = res.findings
    S = P_.segment_summary(F)
    A = U.get_anomalies(res)
    seg_of = dict(zip(F["track_id"], F["segment_id"]))
    S["anomaly_flags"] = S["segment_id"].map(A["track_id"].map(seg_of).value_counts()).fillna(0)
    G = U.get_gaps(res)
    S["evidence_gaps"] = S["segment_id"].map(G["segment_id"].value_counts()).fillna(0)
    c = st.columns(4)
    U.kpi(c[0], "Segments with findings", len(S), f"of {res.summary()['n_segments']} in the data")
    U.kpi(c[1], "Segments with 'Review first'", int((S["review_first"] > 0).sum()), "explainable demo rules", hi=True)
    U.kpi(c[2], "Segments with anomaly flags", int((S["anomaly_flags"] > 0).sum()), "measurements to check")
    U.kpi(c[3], "Segments with evidence gaps", int((S["evidence_gaps"] > 0).sum()), "missing or unresolved evidence")
    st.write("")
    st.plotly_chart(charts.health_heatmap(S), width="stretch", key="hm_heat")
    st.plotly_chart(charts.pipeline_strip(F, res.source.pipeline_length_m), width="stretch", key="hm_strip")
    seg = st.selectbox("Inspect segment", S["segment_id"].tolist(),
                       index=int(S["review_first"].values.argmax()) if len(S) else 0, key="hm_seg")
    row = S[S["segment_id"] == seg].iloc[0]
    st.markdown(f"<div class='cs-card accent'><h4>Segment {seg}</h4><p>{int(row['findings'])} findings, "
                f"{int(row['review_first'])} 'Review first', max latest depth {U.fmt(row['max_latest_pct_wt'], 1)}% WT, "
                f"median observed rate {U.fmt(row['median_rate_likely'], 3)} mm/yr (likely matches), "
                f"{int(row['ambiguous'])} ambiguous, {int(row['anomaly_flags'])} anomaly flags, "
                f"{int(row['evidence_gaps'])} evidence gaps.</p></div>", unsafe_allow_html=True)
    if st.button(f"Open segment {seg} in Defect History", key="hm_open"):
        U.goto("history", hist_seg=seg)
    _track_rows(F, F[F["segment_id"] == seg]["track_id"].tolist(), 8, U.review_store().latest(res.fingerprint))
    with st.expander("Segment table"):
        st.dataframe(S, width="stretch", hide_index=True)


# ============================================================================ INSPECTION INTELLIGENCE
def page_timeline(res):
    U.header(res, "Corrosion Event Timeline",
             "Chronological evidence for one finding. Each event shows where it comes from: the source inspection data, "
             "the current analysis (reconstructed, not historical), or a log the application actually recorded.")
    if not _need(res):
        return
    F = res.findings
    tid = U.pick_finding(F, F["track_id"].tolist(), "Finding", "tl_pick")
    if not tid:
        return
    fp = res.fingerprint
    ev = TL_.build(res, tid, U.review_store().history(fp), U.resolution_log().for_dataset(fp),
                   U.correction_log().for_dataset(fp), U.snapshot_store().list(fp), U.export_log().for_dataset(fp),
                   U.get_anomalies(res))
    g = F.set_index("track_id").loc[tid]
    st.markdown(f"### {tid} &nbsp; {U.cat_chip(g['review_category'])} &nbsp; <span class='muted'>{g['match_status_label']} · "
                f"segment {g['segment_id']}</span>", unsafe_allow_html=True)
    counts = ev["provenance"].value_counts().to_dict()
    st.caption(f"{len(ev)} events · source records: {counts.get('Source record', 0)} · derived by analysis: "
               f"{counts.get('Derived by analysis', 0)} · recorded logs: {counts.get('Recorded log', 0)}. "
               "Forecast or priority revisions appear only when saved snapshots show a change.")
    view = st.radio("View", ["Timeline", "Table"], horizontal=True, key="tl_view", label_visibility="collapsed")
    if view == "Table":
        st.dataframe(ev, width="stretch", hide_index=True)
    else:
        cls = {"Source record": "src", "Recorded log": "log", "Derived by analysis": ""}
        html = "".join(f"<div class='cs-ev {cls.get(r.provenance, '')}'><div class='w'>{escape(str(r.when))} · {escape(r.provenance)}"
                       f" · {escape(str(r.evidence_source))}</div><div class='e'>{escape(r.event)}</div>"
                       f"<div class='v'>{escape(str(r.values))}</div><div class='v'>{escape(str(r.explanation))}</div></div>"
                       for r in ev.itertuples())
        st.markdown(html, unsafe_allow_html=True)
    U.open_buttons(tid, [("identity", "Identity evidence"), ("workbench", "Review in workbench"),
                         ("forecast", "Forecast & priorities")], "tl")


def page_identity(res):
    U.header(res, "Defect Identity Conflicts",
             "Investigate findings whose identity across runs is uncertain: the proposed pairing, every competing candidate, "
             "and the reasons for and against each. Reviewer resolutions are stored separately and never overwrite the algorithm.")
    if not _need(res):
        return
    O = conflict_overview(res)
    if O.empty:
        st.success("No identity uncertainty: every finding is a likely, uncontested match.")
        return
    res_latest = U.get_resolutions(res)
    c = st.columns(4)
    U.kpi(c[0], "Ambiguous", int((O["group"] == "Ambiguous").sum()), "provisional pairings", hi=True)
    U.kpi(c[1], "Unmatched", int((O["group"] == "Unmatched").sum()), "new or not found later")
    U.kpi(c[2], "With competing candidates", int(O["conflicting_candidates"].sum()), "another pairing was possible")
    U.kpi(c[3], "Reviewer resolutions", len(res_latest), "recorded proposals")
    flt = st.radio("Show", ["Ambiguous", "Conflicting candidates", "Likely (contested)", "Unmatched", "All"], horizontal=True,
                   key="id_flt")
    sub = {"All": O, "Ambiguous": O[O["group"] == "Ambiguous"], "Unmatched": O[O["group"] == "Unmatched"],
           "Likely (contested)": O[O["group"] == "Likely"], "Conflicting candidates": O[O["conflicting_candidates"]]}[flt]
    sub = sub.assign(resolution=sub["track_id"].map(lambda t: res_latest.get(t, {}).get("resolution", "")))
    sub = sub.sort_values(["n_candidates", "margin"], ascending=[False, True], na_position="last")
    ev = st.dataframe(sub, width="stretch", hide_index=True, height=260, on_select="rerun", selection_mode="single-row",
                      key=f"id_tbl_{flt}", column_config={"distance": st.column_config.NumberColumn(format="%.2f"),
                                                          "margin": st.column_config.NumberColumn(format="%.2f")})
    U.table_pick(ev, sub, "track_id", f"id_tbl_{flt}")
    tid = U.pick_finding(res.findings, sub["track_id"].tolist(), "Finding", "id_pick")
    if not tid:
        return
    g = res.findings.set_index("track_id").loc[tid]
    st.markdown(f"<div class='cs-card accent'><h4>{tid} - algorithm decision: {g['match_status_label']}</h4><p>{escape(str(g['rationale']))}</p>"
                "<p class='muted'>Normalised distance and agreement index are similarity measures, not calibrated probabilities.</p></div>",
                unsafe_allow_html=True)
    CT = candidate_table(res, tid)
    if CT.empty:
        st.info("No candidate pairs were inside the matching gate for this finding's records.")
    else:
        st.dataframe(CT, width="stretch", hide_index=True,
                     column_config={c: st.column_config.NumberColumn(format="%.3f") for c in
                                    ["raw_dx_m", "offset_m", "aligned_dx_m", "d_clock_h", "distance", "agreement_index"]})
    pos = [p for p in (g["pos_a"], g["pos_b"]) if np.isfinite(p)]
    if pos:
        st.plotly_chart(charts.memory_graph(res.findings, res.match.candidates, (min(pos) - 4, max(pos) + 4), tid,
                                            res.match.run_a, res.match.run_b), width="stretch", key="id_graph")
    st.markdown("##### Record a proposed resolution")
    alts = sorted(set(CT["earlier"].tolist() + CT["later"].tolist()) - {g["obs_a"], g["obs_b"]}) if not CT.empty else []
    with st.form(f"id_form_{tid}"):
        r1, r2 = st.columns(2)
        choice = r1.selectbox("Proposed resolution", RESOLUTION_OPTIONS)
        alt = r2.selectbox("Alternative candidate (if pairing differently)", ["-"] + alts)
        rationale = st.text_area("Rationale (required)")
        allowed = U.can("propose_match_resolution")
        ok = st.form_submit_button("Record resolution", type="primary", disabled=not allowed)
    if not allowed:
        U.deny_note("propose_match_resolution")
    if ok:
        e = U.run_action(ACT.propose_resolution, U.resolution_log(), res.fingerprint, tid, f"{g['obs_a']} -> {g['obs_b']}",
                         g["match_status_label"], choice, "" if alt == "-" else alt, rationale)
        if e is not None:
            st.success("Resolution recorded. The algorithm's pairing, growth and priority are unchanged; the difference is "
                       "listed in the Contradiction Finder and the Evidence Passport.")
    hist = U.resolution_log().for_dataset(res.fingerprint, track_id=tid)
    if hist:
        st.dataframe(pd.DataFrame(hist).drop(columns=["dataset_fingerprint"]).iloc[::-1], width="stretch", hide_index=True)
    U.open_buttons(tid, [("timeline", "Event timeline"), ("workbench", "Review in workbench")], "id")


def page_anomalies(res):
    U.header(res, "Measurement Anomalies",
             "Explainable flags for suspicious measurements: what was observed, the rule it was compared with, why it was "
             "flagged, and what evidence would resolve it. A flag is not a corrosion event. Original values are never changed.")
    if not _need(res):
        return
    cur = U.anomaly_config()
    with st.expander("Check settings (demo assumptions)"):
        with st.form("an_cfg"):
            a1, a2, a3 = st.columns(3)
            z = a1.number_input("Change vs. uncertainty: flag |z| above", 1.0, 10.0, cur.change_z_notable, 0.5)
            rz = a2.number_input("Rate outlier: robust |z| above", 2.0, 10.0, cur.robust_z_outlier, 0.5)
            deep = a3.number_input("Deep relative to WT: % WT above", 30.0, 100.0, cur.deep_pct_wt, 5.0)
            lmm = a1.number_input("Length change: mm above", 5.0, 200.0, cur.length_change_mm, 5.0)
            lfr = a2.number_input("Length change: fraction above", 0.1, 3.0, cur.length_change_frac, 0.1)
            if st.form_submit_button("Apply"):
                st.session_state.anomaly_cfg = AnomalyConfig(z, rz, lmm, lfr, deep).to_dict()
                st.rerun()
        st.caption("Record-level checks reuse the validation rules (missing, invalid, unit-suspect, duplicate). Cross-run checks "
                   "use observed change, stated uncertainty and the population of observed rates (median / MAD).")
    A = U.get_anomalies(res)
    c = st.columns(4)
    U.kpi(c[0], "Flags", len(A), f"{A['track_id'].nunique()} findings")
    U.kpi(c[1], "High", int((A["severity"] == "High").sum()), "verify before relying on the value", hi=True)
    U.kpi(c[2], "Medium", int((A["severity"] == "Medium").sum()), "worth checking")
    U.kpi(c[3], "Low / context", int((A["severity"] == "Low").sum()), "may be genuine")
    f1, f2, f3 = st.columns(3)
    sev = f1.multiselect("Severity", ["High", "Medium", "Low"], default=["High", "Medium", "Low"], key="an_sev")
    chk = f2.multiselect("Check", sorted(A["check"].unique()), key="an_chk", placeholder="All checks")
    srcs = f3.multiselect("Source", sorted(A["source"].unique()), key="an_src", placeholder="All")
    V = A[A["severity"].isin(sev)]
    if chk:
        V = V[V["check"].isin(chk)]
    if srcs:
        V = V[V["source"].isin(srcs)]
    st.dataframe(V, width="stretch", hide_index=True, height=300)
    if V.empty:
        return
    fid = st.selectbox("Open flag", V["flag_id"].tolist(),
                       format_func=lambda f: f"{f} | {V.set_index('flag_id').at[f, 'check']} | {V.set_index('flag_id').at[f, 'observation_id']}",
                       key="an_pick")
    r = V.set_index("flag_id").loc[fid]
    st.markdown(f"<div class='cs-card accent'><h4>{fid} - {escape(r['check'])} ({r['severity']})</h4>"
                f"<div class='cs-vs'><div><b>1 Observed</b><br>{escape(str(r['observed']))}</div>"
                f"<div><b>2 Compared with</b><br>{escape(str(r['comparison']))}</div>"
                f"<div><b>3 Why flagged</b><br>{escape(str(r['reason']))}</div>"
                f"<div><b>4 Review category</b><br>{escape(r['review_category'])}</div>"
                f"<div><b>5 Evidence required</b><br>{escape(r['evidence_required'])}</div>"
                f"<div><b>6 Suggested next step</b><br>{escape(r['next_step'])}</div></div></div>", unsafe_allow_html=True)
    if isinstance(r["track_id"], str):
        U.open_buttons(r["track_id"], [("timeline", "Event timeline"), ("workbench", "Review in workbench")], f"an_{fid}")
    if r["source"] == "validation" and isinstance(r["run_id"], str):
        rec = res.validation.data[(res.validation.data["run_id"] == r["run_id"]) &
                                  (res.validation.data["observation_id"] == r["observation_id"])]
        with st.form(f"an_fix_{fid}"):
            st.markdown("**Propose a correction** (stored separately; the analysis keeps using the original value)")
            k1, k2 = st.columns(2)
            fld = k1.selectbox("Field", ["depth_mm", "axial_position_m", "clock_position_h", "nominal_wt_mm", "length_mm",
                                         "width_mm", "depth_uncertainty_mm"])
            orig = rec[fld].iloc[0] if len(rec) and fld in rec else None
            k2.text_input("Original value (read-only)", value=str(orig), disabled=True)
            prop = k1.text_input("Proposed value")
            why = st.text_area("Rationale / evidence (required)")
            allowed = U.can("propose_correction")
            if st.form_submit_button("Record proposed correction", disabled=not allowed):
                e = U.run_action(ACT.propose_correction, U.correction_log(), res.fingerprint, r["run_id"], r["observation_id"],
                                 fld, None if orig is None or (isinstance(orig, float) and np.isnan(orig)) else float(orig),
                                 prop, why, fid)
                if e is not None:
                    st.success("Proposal recorded. The original value is preserved and still used by the analysis.")
        if not allowed:
            U.deny_note("propose_correction")
    C = U.correction_log().for_dataset(res.fingerprint)
    if C:
        st.markdown("##### Proposed corrections (not applied)")
        st.dataframe(pd.DataFrame(C).drop(columns=["dataset_fingerprint"]).iloc[::-1], width="stretch", hide_index=True)


def page_patterns(res):
    U.header(res, "Corrosion Pattern Explorer",
             "Explore observed patterns by segment, location, clock band, growth category, data quality, match status and "
             "priority. Relationships shown are associations in this dataset, not causes; no soil, pressure or "
             "environmental data is available.")
    if not _need(res):
        return
    E = P_.enrich(res.findings)
    c = st.columns(4)
    segs = c[0].multiselect("Segment", sorted(E["segment_id"].dropna().unique()), key="pt_seg", placeholder="All segments")
    grow = c[1].multiselect("Growth category", sorted(E["growth_category"].dropna().unique()), key="pt_grow", placeholder="All")
    dq = c[2].multiselect("Data quality", ["Flagged", "No flags"], key="pt_dq", placeholder="All")
    run = c[3].selectbox("Present in run", ["Any", res.match.run_a, res.match.run_b, "Both"], key="pt_run")
    V = E
    if segs:
        V = V[V["segment_id"].isin(segs)]
    if grow:
        V = V[V["growth_category"].isin(grow)]
    if dq:
        V = V[V["data_quality"].isin(dq)]
    if run == res.match.run_a:
        V = V[V["obs_a"].notna()]
    elif run == res.match.run_b:
        V = V[V["obs_b"].notna()]
    elif run == "Both":
        V = V[V["obs_a"].notna() & V["obs_b"].notna()]
    st.caption(f"{len(V)} of {len(E)} findings match the filters.")
    colour = st.radio("Colour by", ["review_category", "match_status_label", "growth_category", "data_quality", "clock_band"],
                      horizontal=True, key="pt_col",
                      format_func=lambda x: {"review_category": "Priority", "match_status_label": "Match status",
                                             "growth_category": "Growth category", "data_quality": "Data quality",
                                             "clock_band": "Clock band"}[x])
    paired = V[V["rate_mm_per_yr"].notna()]
    if len(paired):
        st.plotly_chart(charts.pattern_scatter(paired, colour), width="stretch", key="pt_scatter")
    t1, t2, t3 = st.tabs(["Segment comparison", "Spatial clusters", "Association tests"])
    with t1:
        S = P_.segment_summary(V) if len(V) else pd.DataFrame()
        st.dataframe(S, width="stretch", hide_index=True,
                     column_config={"median_rate_likely": st.column_config.NumberColumn(format="%.3f"),
                                    "max_latest_pct_wt": st.column_config.NumberColumn(format="%.1f"),
                                    "share_growth_beyond_noise": st.column_config.NumberColumn(format="%.2f")})
    with t2:
        k1, k2 = st.columns(2)
        gap = k1.slider("Join findings closer than (m)", 2.0, 60.0, 15.0, 1.0, key="pt_gap")
        mn = k2.slider("Minimum findings per cluster", 2, 12, 4, key="pt_min")
        CL, _ = P_.spatial_clusters(V, gap, mn)
        st.caption("Method: single-linkage 1-D grouping by axial position (findings closer than the gap join a cluster). "
                   "Features: position only. Limitations: ignores clock and depth; sensitive to the gap; dense reporting can "
                   "reflect tool sensitivity rather than corrosivity.")
        st.dataframe(CL, width="stretch", hide_index=True,
                     column_config={"median_rate": st.column_config.NumberColumn(format="%.3f"),
                                    "start_m": st.column_config.NumberColumn(format="%.1f"),
                                    "end_m": st.column_config.NumberColumn(format="%.1f"),
                                    "max_latest_pct_wt": st.column_config.NumberColumn(format="%.1f")})
    with t3:
        by = st.selectbox("Compare observed rates across", ["clock_band", "segment_id", "data_quality", "review_category"],
                          key="pt_by")
        a = P_.association(V, by)
        st.markdown(f"<div class='cs-card'><h4>{a['test']} test across {a['groups']} groups</h4><p>H = {U.fmt(a['statistic'], 2)}, "
                    f"p = {U.fmt(a['p_value'], 4)}</p><p>{escape(a['note'])}</p></div>", unsafe_allow_html=True)
        st.caption(DEMO_NOTE)


# ============================================================================ PREDICTION & VALIDATION
def page_whatif(res):
    U.header(res, "What-If Analysis",
             "Re-run the same data with different demo thresholds or forecast settings and see which findings would change "
             "category. Scenarios do not change the current analysis unless you apply them.")
    if not _need(res):
        return
    cur = res.config
    with st.form("wi_form"):
        c = st.columns(3)
        depth = c[0].number_input("Depth review threshold (% WT)", 5.0, 95.0, cur.depth_review_pct_wt, 5.0)
        rate = c[1].number_input("Rate review threshold (mm/yr)", 0.01, 2.0, cur.rate_review_mm_per_yr, 0.05)
        thr = c[2].number_input("Screening threshold (% WT)", 10.0, 95.0, cur.screening_threshold_pct_wt, 5.0)
        hor = c[0].number_input("Projection horizon (yr)", 1.0, 30.0, cur.forecast_horizon_years, 1.0)
        k = c[1].number_input("Noise test k", 1.0, 4.0, cur.noise_k, 0.5)
        meth = c[2].radio("Forecast method", ["baseline", "shrinkage"], index=0 if cur.forecast_method == "baseline" else 1,
                          horizontal=True)
        go_ = st.form_submit_button("Run scenario", type="primary")
    if go_:
        st.session_state.wi_cfg = dict(cur.to_dict(), depth_review_pct_wt=depth, rate_review_mm_per_yr=rate,
                                       screening_threshold_pct_wt=thr, forecast_horizon_years=hor, noise_k=k, forecast_method=meth)
    scen = st.session_state.get("wi_cfg")
    if scen:
        r2 = U.cached_analysis(st.session_state.raw_csv, json.dumps(st.session_state.source), json.dumps(scen),
                               res.match.run_a, res.match.run_b, False)
        a = res.findings.set_index("track_id")["review_category"]
        b = r2.findings.set_index("track_id")["review_category"]
        D = pd.DataFrame({"current": a, "scenario": b}).dropna()
        chg = D[D["current"] != D["scenario"]].reset_index()
        cnt = pd.DataFrame({"current": a.value_counts(), "scenario": b.value_counts()}).reindex(CATEGORIES.values()).fillna(0).astype(int)
        cc = st.columns(2)
        cc[0].dataframe(cnt, width="stretch")
        cc[1].markdown(f"<div class='cs-card accent'><h4>{len(chg)} findings change category</h4><p>Changed settings: "
                       + ", ".join(f"{kk}: {cur.to_dict()[kk]} -> {vv}" for kk, vv in scen.items() if cur.to_dict()[kk] != vv)
                       + "</p></div>", unsafe_allow_html=True)
        if len(chg):
            why = r2.findings.set_index("track_id")["priority_explanation"].str.split(" \\| ").str[0]
            chg["scenario_first_reason"] = chg["track_id"].map(why)
            st.dataframe(chg, width="stretch", hide_index=True)
        allowed = U.can("change_analysis_settings")
        if st.button("Apply scenario as the current analysis settings", key="wi_apply", disabled=not allowed):
            if U.run_action(ACT.change_settings, cur.to_dict(), scen, res.fingerprint) is not None:
                st.session_state.cfg = scen
                st.session_state.pop("wi_cfg", None)
                st.rerun()
        if not allowed:
            U.deny_note("change_analysis_settings")
    st.markdown("##### Single-finding measurement sensitivity (depth rule C1 only)")
    F = res.findings[np.isfinite(res.findings["latest_pct_wt"])]
    tid = U.pick_finding(res.findings, F["track_id"].tolist(), "Finding", "wi_pick")
    if tid:
        g = res.findings.set_index("track_id").loc[tid]
        u = g["u_b"] if g["depth_valid_b"] else g["u_a"]
        thr_mm = cur.depth_review_pct_wt / 100 * g["wt_mm"]
        rows = []
        for lab, dv in (("measured - k sigma", g["latest_depth_mm"] - cur.noise_k * u if np.isfinite(u) else np.nan),
                        ("as measured", g["latest_depth_mm"]),
                        ("measured + k sigma", g["latest_depth_mm"] + cur.noise_k * u if np.isfinite(u) else np.nan)):
            rows.append(dict(case=lab, depth_mm=dv, pct_wt=dv / g["wt_mm"] * 100,
                             C1_triggered=("n/a (uncertainty unknown)" if not np.isfinite(dv) else bool(dv >= thr_mm))))
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
                     column_config={"depth_mm": st.column_config.NumberColumn(format="%.2f"),
                                    "pct_wt": st.column_config.NumberColumn(format="%.1f")})
        st.caption(f"Threshold {thr_mm:.2f} mm ({cur.depth_review_pct_wt:g}% of {g['wt_mm']:.1f} mm). Other rules (growth, "
                   "projection, evidence) are not re-evaluated in this view.")


def page_arena(res):
    U.header(res, "Model Challenge Arena",
             "Growth-rate estimators compared on held-out synthetic defects. Results describe the fictional dataset only "
             "and do not establish real-world accuracy. They do not change the prioritisation rules.")
    if not _need(res):
        return
    ar = U.get_arena(res)
    if ar is None:
        st.info("The arena needs the synthetic ground-truth file, which exists only for the demo dataset. Load the demo "
                "dataset to compare methods. For uploaded data, no accuracy can be measured.")
        return
    if not ar.get("ok"):
        st.warning(ar.get("reason"))
        return
    with st.expander("How the evaluation works", expanded=False):
        st.markdown(
            f"- **Ground truth:** the generator draws each defect's true constant growth rate (about 35% inactive), simulates "
            f"two tools with stated 1-sigma sizing noise, odometer drift and detection limits. Truth is read only here.\n"
            f"- **Records:** {ar['n_records']} likely matches whose two records are truly the same defect, with known uncertainty.\n"
            f"- **Split:** group-wise by true defect, {int(ar['test_frac'] * 100)}% test, repeated over {ar['seeds']} seeds. "
            "Population mean, between-defect variance and segment means are fitted on training defects only; each test defect "
            "is estimated from its own two measurements plus those fitted values (no leakage).\n"
            f"- **Metrics:** MAE, RMSE and bias in mm/yr against the true rate; coverage = share of true rates inside the "
            f"{ar['k']:g}-sigma interval. Coverage is optimistic because synthetic noise matches the stated uncertainty.")
    S = ar["summary"].sort_values("rmse")
    best = S.iloc[0]
    c = st.columns(4)
    U.kpi(c[0], "Lowest mean RMSE", f"<span style='font-size:1.05rem'>{best['method_name']}</span>",
          f"{best['rmse']:.4f} mm/yr", hi=True)
    U.kpi(c[1], "Baseline RMSE", f"{S.set_index('method').at['B1', 'rmse']:.4f}", "per-defect observed rate")
    U.kpi(c[2], "Test defects per split", int(best["n_test"]), f"{ar['seeds']} splits")
    U.kpi(c[3], "Evaluable records", ar["n_records"], "synthetic only")
    st.plotly_chart(charts.arena_bars(S), width="stretch", key="ar_bars")
    st.dataframe(S[["method", "method_name", "mae", "mae_sd", "rmse", "rmse_sd", "bias", "coverage", "lowest_rmse_in_splits"]],
                 width="stretch", hide_index=True,
                 column_config={c: st.column_config.NumberColumn(format="%.4f") for c in ["mae", "mae_sd", "rmse", "rmse_sd", "bias"]}
                 | {"coverage": st.column_config.NumberColumn(format="%.3f")})
    st.markdown("##### Where each method does well (MAE by true-rate group, first split)")
    st.dataframe(ar["by_group"].rename(columns=METHODS), width="stretch", hide_index=True)
    st.markdown("##### Strengths and failure modes")
    st.dataframe(pd.DataFrame([dict(method=f"{k} {METHODS[k]}", performs_well=v[0], may_fail=v[1]) for k, v in STRENGTHS.items()]),
                 width="stretch", hide_index=True)
    st.caption(f"The application currently uses the '{res.config.forecast_method}' forecast method (change under Analysis settings). "
               "A more complex estimator is not assumed to be better: compare the error and coverage above.")


def page_contradictions(res):
    U.header(res, "Contradiction Finder",
             "Findings where pieces of evidence disagree, shown side by side with what would resolve them. No single "
             "confidence score is computed, and nothing here decides whether the pipeline is safe.")
    if not _need(res):
        return
    K = U.get_contradictions(res)
    if K.empty:
        st.success("Rules K1-K8 found no contradictions in the current analysis.")
        return
    counts = K["rule"].value_counts()
    c = st.columns(4)
    U.kpi(c[0], "Contradictions", len(K), f"{K['track_id'].nunique()} findings", hi=True)
    U.kpi(c[1], "Identity-related", int(counts.get("K1", 0) + counts.get("K8", 0)), "K1, K8")
    U.kpi(c[2], "Measurement-related", int(counts.get("K2", 0) + counts.get("K4", 0) + counts.get("K5", 0) + counts.get("K6", 0)),
          "K2, K4, K5, K6")
    U.kpi(c[3], "Assumption / reviewer", int(counts.get("K3", 0) + counts.get("K7", 0)), "K3, K7")
    with st.expander("Rules"):
        st.dataframe(pd.DataFrame([dict(rule=k, meaning=v) for k, v in RULES.items()]), width="stretch", hide_index=True)
    f1, f2 = st.columns(2)
    rules = f1.multiselect("Rule", list(RULES), format_func=lambda r: f"{r} {RULES[r]}", key="ct_rule", placeholder="All rules")
    cats = f2.multiselect("Review category", list(CATEGORIES.values()), key="ct_cat", placeholder="All")
    V = K
    if rules:
        V = V[V["rule"].isin(rules)]
    if cats:
        V = V[V["review_category"].isin(cats)]
    n = st.slider("Shown", 1, max(1, len(V)), min(12, max(1, len(V))), key="ct_n") if len(V) > 1 else len(V)
    for i, r in enumerate(V.head(n).itertuples()):
        st.markdown(f"<div class='cs-card accent'><h4>{r.track_id} &middot; {r.rule} {escape(r.title)} &nbsp;"
                    f"{U.cat_chip(r.review_category)}</h4><div class='cs-vs'><div><b>Evidence A</b><br>{escape(str(r.evidence_a))}</div>"
                    f"<div><b>Evidence B</b><br>{escape(str(r.evidence_b))}</div></div><p style='margin-top:0.45rem'><b>Conflict:</b> "
                    f"{escape(r.conflict)}</p><p><b>Would help resolve:</b> {escape(r.resolve_with)}</p></div>", unsafe_allow_html=True)
        U.open_buttons(r.track_id, [("timeline", "Timeline"), ("identity", "Identity"), ("workbench", "Workbench")], f"ct{i}")


# ============================================================================ PLANNING & REVIEW
def page_strategy(res):
    U.header(res, "Inspection Strategy Simulator",
             "Compare hypothetical ways to spend a review / investigation budget. Costs, budgets and capacities are "
             "assumptions; outcomes describe coverage of findings and uncertainty, not reduced failure risk. Nothing is "
             "authorised or scheduled.")
    if not _need(res):
        return
    with st.form("sg_form"):
        c = st.columns(4)
        budget = c[0].number_input("Hypothetical budget", 0.0, 10_000_000.0, 40_000.0, 1000.0)
        cap = c[1].number_input("Capacity (findings)", 1, 2000, 40, 1)
        ce = c[2].number_input("Cost: engineering review", 0.0, 1_000_000.0, 1500.0, 100.0)
        cv = c[3].number_input("Cost: verification / data request", 0.0, 1_000_000.0, 600.0, 50.0)
        elig = st.multiselect("Eligible review categories", list(CATEGORIES.values())[:4], default=list(CATEGORIES.values())[:4])
        allowed = U.can("create_planning_scenario")
        sub = st.form_submit_button("Simulate", type="primary", disabled=not allowed)
    if not allowed:
        U.deny_note("create_planning_scenario")
        st.caption("Showing the default scenario (read-only).")
    if sub:
        U.run_action(ACT.planning_scenario, "strategy simulator",
                     f"budget {budget:,.0f}; capacity {int(cap)}; review {ce:,.0f}; verification {cv:,.0f}", res.fingerprint)
    sim = ST_.simulate(res.findings, U.get_anomalies(res), U.get_contradictions(res),
                       ST_.StrategyInputs(budget, int(cap), ce, cv, elig))
    R = sim["results"]
    st.plotly_chart(charts.strategy_bars(R), width="stretch", key="sg_bars")
    T = pd.DataFrame([dict(strategy=v["name"], findings_covered=v["findings_covered"], budget_used=v["budget_used"],
                           review_first=f"{v['review_first_covered']}/{v['review_first_total']}",
                           uncertainty_covered=v["uncertainty_covered"], uncertainty_remaining=v["uncertainty_remaining"],
                           ambiguous_remaining=v["ambiguous_remaining"], quality_flags_remaining=v["quality_issues_remaining"],
                           contradictions_remaining=v["contradictions_remaining"]) for v in R.values()])
    st.dataframe(T, width="stretch", hide_index=True, column_config={"budget_used": st.column_config.NumberColumn(format="%.0f")})
    fname = f"CorroSight_strategy_summary_{res.fingerprint[:8]}.csv"
    if U.can("export_planning"):
        st.download_button("Download planning summary CSV", T.to_csv(index=False).encode("utf-8"), fname, "text/csv",
                           key="sg_dl", on_click=ACT.export,
                           args=(U.current_user(), U.audit_log(), "Strategy planning summary", fname, res.fingerprint, True))
    else:
        st.button("Download planning summary CSV", disabled=True, key="sg_dl_off", help=rbac.explain("export_planning"))
    tabs = st.tabs([v["name"].split(":")[0] for v in R.values()])
    pool = sim["pool"].set_index("track_id")
    for tab, v in zip(tabs, R.values()):
        with tab:
            sel = pool.loc[v["selected"]].reset_index() if v["selected"] else pd.DataFrame()
            if len(sel):
                st.dataframe(sel[["track_id", "review_category", "match_status_label", "uncertainty_score", "cost",
                                  "proposed_next_step"]], width="stretch", hide_index=True)
            else:
                st.info("Nothing fits the budget and capacity.")
    with st.expander("Assumptions and scoring"):
        st.markdown(ST_.__doc__)
    st.caption("The budget-constrained optimiser (knapsack) is still available on Evidence & Planning > Budget planner.")


def page_workbench(res):
    U.header(res, "Engineering Review Workbench",
             "Open a finding, review its evidence, and record a decision with a reason. Earlier decisions are kept; a review "
             "can be reopened. A recommendation, a reviewer decision and a verified repair are different things: closing a "
             "review does not mean the defect was repaired.")
    if not _need(res):
        return
    F = res.findings
    store = U.review_store()
    latest = store.latest(res.fingerprint)
    q = F[["priority_order", "track_id", "review_category", "match_status_label", "segment_id", "proposed_next_step"]].copy()
    q["review_status"] = q["track_id"].map(lambda t: latest.get(t, {}).get("status", "Not reviewed"))
    q["assigned_to"] = q["track_id"].map(lambda t: latest.get(t, {}).get("assigned_to", ""))
    c = st.columns(5)
    for col, s in zip(c, ["Not reviewed"] + WORKBENCH_STATUSES[:4]):
        U.kpi(col, s, int((q["review_status"] == s).sum()), "findings", hi=s == "Not reviewed")
    f1, f2 = st.columns(2)
    stf = f1.multiselect("Status", sorted(q["review_status"].unique()), key="wb_status", placeholder="All statuses")
    caf = f2.multiselect("Review category", list(CATEGORIES.values()), default=list(CATEGORIES.values())[:4], key="wb_cat")
    V = q
    if stf:
        V = V[V["review_status"].isin(stf)]
    if caf:
        V = V[V["review_category"].isin(caf)]
    ev = st.dataframe(V, width="stretch", hide_index=True, height=240, on_select="rerun", selection_mode="single-row", key="wb_tbl")
    U.table_pick(ev, V, "track_id", "wb_tbl")
    tid = U.pick_finding(F, V["track_id"].tolist(), "Open finding", "wb_pick")
    if not tid:
        return
    g = F.set_index("track_id").loc[tid]
    st.markdown(f"### {tid} &nbsp; {U.cat_chip(g['review_category'])} &nbsp; <span class='muted'>Status: "
                f"{latest.get(tid, {}).get('status', 'Not reviewed')}</span>", unsafe_allow_html=True)
    t1, t2, t3, t4, t5 = st.tabs(["Source & match", "Validation warnings", "Growth & forecast", "Priority rationale", "Contradictions & gaps"])
    with t1:
        U.finding_evidence(res, tid, show_title=False)
    with t2:
        A = U.get_anomalies(res)
        a = A[A["track_id"] == tid]
        st.dataframe(a, width="stretch", hide_index=True) if len(a) else st.success("No measurement anomaly flags for this finding.")
        flags = "; ".join(x for x in (g["flags_a"], g["flags_b"]) if isinstance(x, str) and x)
        st.caption(f"Record-level validation flags: {flags or 'none'}")
    with t3:
        st.markdown(f"<div class='cs-card'><span class='tag t-calc'>CALCULATED</span> change {U.fmt(g['delta_mm'])} mm over "
                    f"{U.fmt(g['dt_years'])} yr = {U.fmt(g['rate_mm_per_yr'], 3)} mm/yr ({g['change_class_label']})<br>"
                    f"<span class='tag t-pred'>PREDICTED</span> {g['forecast_status_label']}: central {U.fmt(g['proj_depth_central_mm'])} mm, "
                    f"upper {U.fmt(g['proj_depth_upper_mm'])} mm at +{res.config.forecast_horizon_years:g} yr<br>"
                    f"<span class='tag t-unc'>UNCERTAIN</span> {escape(str(g['forecast_reason']))}</div>", unsafe_allow_html=True)
    with t4:
        st.markdown("\n".join(f"- {x}" for x in str(g["priority_explanation"]).split(" | ")))
        st.caption(f"Readiness: {g['readiness_label']}. Missing: {g['inputs_missing'] or 'none'}.")
    with t5:
        K = U.get_contradictions(res)
        k = K[K["track_id"] == tid]
        st.dataframe(k, width="stretch", hide_index=True) if len(k) else st.info("No contradictions for this finding.")
        G = U.get_gaps(res)
        gg = G[G["track_id"] == tid]
        st.dataframe(gg, width="stretch", hide_index=True) if len(gg) else st.info("No evidence gaps listed.")
    st.markdown("#### Record decision")
    U.review_form(res, tid, "wb")
    prev = latest.get(tid)
    if prev and prev["status"] in ("Reviewed", CLOSED_STATUS) or (prev and prev["status"] not in WORKBENCH_STATUSES):
        with st.form(f"wb_reopen_{tid}"):
            st.markdown(f"**Reopen this review** (current status: {prev['status']}). The earlier decision stays in the log.")
            why = st.text_input("Reason for reopening")
            allowed = U.can("reopen_review")
            if st.form_submit_button("Reopen review", disabled=not allowed):
                if not why.strip():
                    st.error("A reason is required to reopen a review.")
                elif U.run_action(ACT.reopen_review, store, res.fingerprint, tid, why) is not None:
                    st.success("Reopened: status set to 'Under Review'.")
                    st.rerun()
        if not allowed:
            U.deny_note("reopen_review")
    U.open_buttons(tid, [("timeline", "Event timeline"), ("identity", "Identity evidence"), ("passport", "Evidence Passport")], "wb")


def page_gaps(res):
    U.header(res, "Evidence Gap Finder",
             "What is missing or unresolved for each finding, and which data requests would unblock the most findings. "
             "Missing data is never treated as 'no concern'.")
    if not _need(res):
        return
    G = U.get_gaps(res)
    UO = unlock_opportunities(res.findings)
    c = st.columns(4)
    U.kpi(c[0], "Evidence gaps", len(G), f"{G['track_id'].nunique()} findings", hi=True)
    U.kpi(c[1], "Missing engineering inputs", int((G["gap_type"] == "Missing engineering input").sum()), "readiness inputs")
    U.kpi(c[2], "Identity unresolved", int((G["gap_type"] == "Defect identity unresolved").sum()), "ambiguous matches")
    U.kpi(c[3], "Single observations", int((G["gap_type"] == "Single observation (no growth history)").sum()), "no growth history")
    st.markdown("##### Data requests that unblock the most findings")
    st.caption("Counts findings for which this is the only missing readiness input.")
    st.dataframe(UO, width="stretch", hide_index=True)
    st.markdown("##### Gaps by type and segment")
    pv = G.pivot_table(index="segment_id", columns="gap_type", values="track_id", aggfunc="count", fill_value=0)
    st.dataframe(pv, width="stretch")
    gt = st.multiselect("Gap type", sorted(G["gap_type"].unique()), key="gp_type", placeholder="All gap types")
    V = G[G["gap_type"].isin(gt)] if gt else G
    ev = st.dataframe(V, width="stretch", hide_index=True, height=300, on_select="rerun", selection_mode="single-row", key="gp_tbl")
    U.table_pick(ev, V, "track_id", "gp_tbl")
    if st.session_state.get("focus_track") in set(V["track_id"]):
        U.open_buttons(st.session_state.focus_track, [("workbench", "Review in workbench"), ("timeline", "Event timeline")], "gp")


# ============================================================================ TRUST & EVIDENCE
def page_trust(res):
    U.header(res, "Data Trust Scorecard",
             "Completeness, validity and consistency of the loaded inspection data, as separate transparent percentages. "
             "No composite confidence score is computed. Bands (Good / Fair / Poor) are display conventions, not engineering criteria.")
    if not _need(res):
        return
    T = trust_scorecard(res)
    comp, val, con = T["completeness"], T["validity"], T["consistency"]
    c = st.columns(4)
    U.kpi(c[0], "Depth valid", f"{val['depth_valid'].mean():.1f}%", band(val["depth_valid"].mean()), hi=True)
    U.kpi(c[1], "Uncertainty stated", f"{val['uncertainty_stated'].mean():.1f}%", band(val["uncertainty_stated"].mean()))
    U.kpi(c[2], "Wall thickness valid", f"{val['wall_thickness_valid'].mean():.1f}%", band(val["wall_thickness_valid"].mean()))
    U.kpi(c[3], "Earlier records matched", f"{con.iloc[0]['value']:.1f}%", "likely matches")
    st.plotly_chart(charts.pct_bars(comp, "run_id", "Field completeness by run (% of records with a value)"), width="stretch",
                    key="tr_comp")
    st.dataframe(comp, width="stretch", hide_index=True,
                 column_config={c: st.column_config.NumberColumn(format="%.1f") for c in comp.columns if c not in ("run_id", "records")})
    st.plotly_chart(charts.pct_bars(val, "run_id", "Validity by run (% of records passing each check)"), width="stretch", key="tr_val")
    con = con.assign(band=con.apply(lambda r: band(r["value"]) if r["measure"].startswith(("Earlier", "Segments")) else "context", axis=1))
    st.dataframe(con, width="stretch", hide_index=True, column_config={"value": st.column_config.NumberColumn(format="%.1f")})
    with st.expander("By segment"):
        st.dataframe(T["segments"], width="stretch", hide_index=True,
                     column_config={c: st.column_config.NumberColumn(format="%.1f") for c in ["depth_valid", "wt_valid",
                                                                                               "uncertainty_stated", "flagged"]})


def page_assistant(res):
    U.header(res, "Evidence-Grounded Assistant",
             "Ask about the loaded analysis. Answers are retrieved from the application's own records and calculations by "
             "local rules; no language model or external AI service is connected, and no data leaves this computer.")
    if not _need(res):
        return
    fp = res.fingerprint
    ctx = A_.Context(res, U.review_store().latest(fp), U.get_contradictions(res), U.get_anomalies(res), U.get_arena(res),
                     U.snapshot_store().list(fp))
    hist = st.session_state.setdefault("chat", [])
    st.markdown("**Try:**")
    cols = st.columns(3)
    for i, q in enumerate(A_.EXAMPLES[:9]):
        if cols[i % 3].button(q, key=f"as_ex_{i}", width="stretch"):
            hist.append((q, A_.ask(q, ctx)))
    q = st.chat_input("Ask about a finding (e.g. 'Why was T0177 prioritised?'), a segment, methods or snapshots")
    if q:
        hist.append((q, A_.ask(q, ctx)))
    for j, (qq, ans) in enumerate(reversed(hist[-8:])):
        with st.chat_message("user"):
            st.markdown(qq)
        with st.chat_message("assistant"):
            if not ans.grounded:
                st.caption("Insufficient evidence in the loaded analysis")
            st.markdown(ans.text)
            if ans.refs:
                cs = st.columns(min(4, len(ans.refs)))
                for k, t in enumerate(ans.refs[:4]):
                    if cs[k].button(f"Open {t}", key=f"as_open_{j}_{k}_{t}"):
                        U.goto("workbench", t)
    if hist and st.button("Clear conversation", key="as_clear"):
        st.session_state.chat = []
        st.rerun()


def _raw_and_source():
    return read_csv(st.session_state.raw_csv.encode("utf-8")), SourceInfo(**st.session_state.source)


def page_snapshots(res):
    U.header(res, "Reproducible Analysis Snapshots",
             "Save the exact configuration and results of an analysis, revisit it, replay it on the same data, and compare two "
             "snapshots. Snapshots are appended, never overwritten. Exporting a PDF alone does not make an analysis reproducible.")
    if not _need(res):
        return
    store = U.snapshot_store()
    with st.form("sn_save"):
        note = st.text_input("Note (what is this snapshot for?)")
        allowed = U.can("save_snapshot")
        if st.form_submit_button("Save snapshot of the current analysis", type="primary", disabled=not allowed):
            e = U.run_action(ACT.save_snapshot, store, res, U.review_store().latest(res.fingerprint), note)
            if e is not None:
                st.success(f"Saved {e['snapshot_id']} (created by {e['created_by']}).")
    if not allowed:
        U.deny_note("save_snapshot")
    snaps = store.list(res.fingerprint)
    if not snaps:
        st.info("No snapshots saved for this dataset yet.")
        return
    L = pd.DataFrame([dict(snapshot_id=s["snapshot_id"], time=s["timestamp_utc"], note=s["note"], by=s["created_by"],
                           runs=f"{s['runs']['run_a']}->{s['runs']['run_b']}", method=s["config"].get("forecast_method"),
                           review_first=s["summary"]["review_counts"].get("Review first", 0), software=s["software_version"],
                           git=s["git_commit"][:12], digest=s["findings_digest"][:12]) for s in snaps])
    st.dataframe(L.iloc[::-1], width="stretch", hide_index=True)
    ids = [s["snapshot_id"] for s in snaps]
    sid = st.selectbox("Snapshot", ids[::-1], key="sn_pick")
    s = store.get(sid)
    t1, t2, t3 = st.tabs(["Details", "Replay", "Compare"])
    with t1:
        st.json({k: s[k] for k in ("snapshot_id", "timestamp_utc", "dataset_fingerprint", "runs", "source", "software_version",
                                   "algorithm_versions", "git_commit", "findings_digest", "summary", "config", "replay_requirements")},
                expanded=False)
        st.caption(f"{len(s['findings'])} findings and {len(s['reviews'])} review decisions recorded in this snapshot.")
    with t2:
        if st.button("Replay this snapshot on the loaded data", key="sn_replay"):
            raw, src = _raw_and_source()
            out = S_.replay(s, raw, src, run_analysis)
            U.run_action(ACT.snapshot_event, "snapshot_replayed", sid, res.fingerprint, out["status"])
            (st.success if out["exact"] else st.warning)(out["status"])
            for m in out["missing"] + out["differences"]:
                st.markdown(f"- {m}")
            if out["exact"]:
                st.caption(f"Recomputed findings digest {out['new_digest'][:16]}... equals the stored digest.")
    with t3:
        if len(ids) < 2:
            st.info("Save a second snapshot (for example after changing a setting) to compare.")
        else:
            c1, c2 = st.columns(2)
            a = c1.selectbox("Before", ids, index=len(ids) - 2, key="sn_a")
            b = c2.selectbox("After", ids, index=len(ids) - 1, key="sn_b")
            C = S_.compare(store.get(a), store.get(b))
            if st.session_state.get("_sn_cmp_logged") != (a, b):
                st.session_state["_sn_cmp_logged"] = (a, b)
                U.run_action(ACT.snapshot_event, "snapshot_compared", f"{a} vs {b}", res.fingerprint)
            for title, key in (("Data, software and algorithm changes", "metadata"), ("Setting changes", "config"),
                               ("Findings that changed", "findings"), ("Review status changes", "reviews")):
                st.markdown(f"##### {title} ({len(C[key])})")
                if len(C[key]):
                    st.dataframe(C[key].astype(str), width="stretch", hide_index=True)
                else:
                    st.caption("None.")


def page_passport_audit(res):
    U.header(res, "Evidence Passport & Audit Trail",
             "Generate the PDF / CSV Evidence Passport and inspect every recorded action for this dataset. The passport "
             "records analysis and review evidence; it does not certify pipeline safety or regulatory compliance.")
    if not _need(res):
        return
    t1, t2 = st.tabs(["Evidence Passport", "Audit trail"])
    with t1:
        U.passport_tab(res)
    with t2:
        fp = res.fingerprint
        if not U.can("view_audit"):
            st.error(rbac.explain("view_audit"))
            return
        ev = U.audit_log().for_dataset(fp)
        st.markdown(f"##### User-attributed events for this dataset ({len(ev)})")
        if ev:
            E = pd.DataFrame(ev)
            st.dataframe(E[["timestamp_utc", "event_id", "username", "user_role", "action_label", "resource", "details"]].iloc[::-1],
                         width="stretch", hide_index=True)
        else:
            st.caption("No user-attributed events for this dataset yet.")
        st.markdown("##### Combined evidence log")
        rows = []
        for e in U.review_store().history(fp):
            rows.append(dict(time=e["timestamp_utc"], type="Review" + (" (reopened)" if e.get("action") == "reopened" else ""),
                             item=e["track_id"], who=e["reviewer"] + (f" ({e['user_role']})" if e.get("user_role") else ""), detail=f"{e['status']}; {e.get('reason') or e.get('notes') or ''}"))
        for e in U.resolution_log().for_dataset(fp):
            rows.append(dict(time=e["timestamp_utc"], type="Identity resolution", item=e["track_id"], who=e["reviewer"],
                             detail=f"{e['resolution']} {e.get('alternative', '')}; {e['rationale']}"))
        for e in U.correction_log().for_dataset(fp):
            rows.append(dict(time=e["timestamp_utc"], type="Correction proposal (not applied)", item=f"{e['run_id']}/{e['observation_id']}",
                             who=e["reviewer"], detail=f"{e['field']}: {e['original_value']} -> {e['proposed_value']}; {e['rationale']}"))
        for e in U.snapshot_store().list(fp):
            rows.append(dict(time=e["timestamp_utc"], type="Snapshot", item=e["snapshot_id"], who=e["created_by"], detail=e["note"]))
        for e in U.export_log().for_dataset(fp):
            rows.append(dict(time=e["timestamp_utc"], type="Export", item=e["kind"], who="-",
                             detail=f"{e.get('file', '')}; snapshot {e.get('snapshot_id') or '-'}"))
        if not rows:
            st.info("Nothing has been recorded for this dataset yet.")
            return
        AT = pd.DataFrame(rows).sort_values("time", ascending=False)
        st.dataframe(AT, width="stretch", hide_index=True)
        st.download_button("Download audit trail CSV", AT.to_csv(index=False).encode("utf-8"),
                           f"CorroSight_audit_{fp[:8]}.csv", "text/csv", key="au_dl",
                           on_click=U.audit_log().record,
                           args=(U.current_user(), "export", "Audit trail CSV", f"CorroSight_audit_{fp[:8]}.csv", fp))
        st.caption("Logs are append-only JSON files in the outputs folder; entries are never edited by the application.")


# ============================================================================ ROLE HOME DASHBOARDS
_ROLE_LINKS = {
    "engineer": [("workbench", "Review workbench"), ("forecast", "Forecast & priorities"), ("contradictions", "Contradictions"),
                 ("passport", "Evidence Passport")],
    "analyst": [("anomalies", "Measurement anomalies"), ("identity", "Identity conflicts"), ("trust", "Data trust"),
                ("arena", "Model arena")],
    "planner": [("strategy", "Strategy simulator"), ("planning", "Budget planner"), ("gaps", "Evidence gaps"),
                ("workbench", "Review status")],
    "manager": [("overview", "Pipeline overview"), ("workbench", "Review progress"), ("snapshots", "Snapshots"),
                ("passport", "Evidence Passport & audit")],
}


def _links(role: str):
    items = [(k, lab) for k, lab in _ROLE_LINKS[role] if rbac.can_view(U.current_user(), k)]
    cols = st.columns(len(items))
    for c, (k, lab) in zip(cols, items):
        if c.button(lab, key=f"home_go_{k}", width="stretch"):
            U.goto(k)


def page_home(res):
    """Role-specific start page. Every number comes from the loaded analysis and the shared logs."""
    u = U.current_user()
    role = u["role"]
    info = rbac.ROLES[role]
    U.topbar("Home", None if res is None else res.source.synthetic)
    st.markdown(f"## Welcome, {escape(u['display_name'])}")
    st.markdown(f"<div class='cs-desc'><b>{escape(info['title'])}.</b> {escape(info['purpose'])}</div>", unsafe_allow_html=True)
    if res is None:
        st.info("No inspection data is loaded in this session yet.")
        if st.button("Load demo dataset", type="primary", key="landing_demo"):
            if U.load_demo_as_user():
                st.rerun()
        st.caption("Or use the data controls in the sidebar." + ("" if U.can("upload_data") else
                                                                 " Uploading new data is limited to engineers and data analysts."))
        return
    if not res.ok:
        st.warning("The loaded data cannot be analysed yet; see Pipeline Overview for blocking issues.")
        return
    if res.source.synthetic:
        st.markdown("<div class='cs-banner'><b>SYNTHETIC DEMO DATA.</b> Fictional pipeline; results do not describe a real asset."
                    "</div>", unsafe_allow_html=True)
    F, s, fp = res.findings, res.summary(), res.fingerprint
    latest = U.review_store().latest(fp)
    status = F["track_id"].map(lambda t: latest.get(t, {}).get("status", "Not reviewed"))
    rc = s["review_counts"]
    first = F[F["review_category"] == "Review first"]
    first_open = int((status[first.index] == "Not reviewed").sum()) if len(first) else 0
    A, K = U.get_anomalies(res), U.get_contradictions(res)
    amb = int(s["match_counts"].get("AMBIGUOUS", 0))
    c = st.columns(4)
    if role == "engineer":
        U.kpi(c[0], "Review first", rc.get("Review first", 0), f"{first_open} not yet reviewed", hi=True)
        U.kpi(c[1], "Decisions recorded", len(latest), f"of {len(F)} findings")
        U.kpi(c[2], "Contradictions", len(K), f"{K['track_id'].nunique() if len(K) else 0} findings")
        U.kpi(c[3], "Ambiguous matches", amb, "identity unresolved")
        _links(role)
        st.markdown("##### Highest-priority findings and their review status")
        _track_rows(F, first["track_id"].tolist() or F["track_id"].tolist(), 8, latest)
        st.caption("Recording a review decision documents engineering judgement; it does not approve repairs, operating "
                   "changes or certify pipeline safety.")
    elif role == "analyst":
        ic = s["issue_counts"]
        U.kpi(c[0], "Validation errors", ic["Error"], f"{ic['Warning']} warnings", hi=True)
        U.kpi(c[1], "Anomaly flags", len(A), f"{int((A['severity'] == 'High').sum()) if len(A) else 0} high")
        U.kpi(c[2], "Likely matches", s["match_counts"].get("LIKELY_MATCH", 0), f"{amb} ambiguous")
        U.kpi(c[3], "Corrections proposed", len(U.correction_log().for_dataset(fp)), "original values kept")
        _links(role)
        st.markdown("##### Matching outcome")
        st.dataframe(pd.DataFrame([dict(status=k, findings=v) for k, v in s["match_counts"].items()]), width="stretch",
                     hide_index=True)
        if res.evaluation:
            st.caption("Post-hoc evaluation against synthetic ground truth is available on the Model Challenge Arena page.")
        if len(A):
            st.markdown("##### High-severity anomaly flags")
            st.dataframe(A[A["severity"] == "High"].head(15), width="stretch", hide_index=True)
    elif role == "planner":
        G = U.get_gaps(res)
        open_tasks = int(status.isin(["Not reviewed", "Awaiting Review", "Under Review"]).sum())
        U.kpi(c[0], "Review first", rc.get("Review first", 0), f"{rc.get('Verify data first', 0)} verify data first", hi=True)
        U.kpi(c[1], "Outstanding reviews", open_tasks, "not reviewed / awaiting / under review")
        U.kpi(c[2], "Awaiting evidence", int((status == "Additional Evidence Required").sum()), "additional evidence required")
        U.kpi(c[3], "Unresolved identity", amb, "ambiguous matches")
        _links(role)
        st.markdown("##### Review categories")
        st.dataframe(pd.DataFrame([dict(category=k, findings=rc.get(k, 0)) for k in CATEGORIES.values()]), width="stretch",
                     hide_index=True)
        st.markdown("##### Data requests that unblock the most findings")
        st.dataframe(unlock_opportunities(F).head(10), width="stretch", hide_index=True)
        st.caption(f"{len(G)} evidence gaps in total. Planning outputs are candidate plans for people to decide on; nothing is "
                   "scheduled or authorised by CorroSight.")
    else:  # manager
        reviewed = int(status.isin(["Reviewed", "Closed with Documented Rationale"]).sum())
        U.kpi(c[0], "Findings", len(F), f"{rc.get('Review first', 0)} review first", hi=True)
        U.kpi(c[1], "Review progress", f"{reviewed}/{len(F)}", "reviewed or closed with rationale")
        U.kpi(c[2], "Data quality", f"{s['issue_counts']['Error']} errors", f"{s['issue_counts']['Warning']} warnings")
        U.kpi(c[3], "Snapshots", len(U.snapshot_store().list(fp)), "reproducible analyses saved")
        _links(role)
        cc = st.columns(2)
        cc[0].markdown("##### Priority distribution")
        cc[0].dataframe(pd.DataFrame([dict(category=k, findings=rc.get(k, 0)) for k in CATEGORIES.values()]),
                        width="stretch", hide_index=True)
        cc[1].markdown("##### Review status")
        cc[1].dataframe(status.value_counts().rename_axis("status").reset_index(name="findings"), width="stretch",
                        hide_index=True)
        ev = U.audit_log().for_dataset(fp)
        st.markdown("##### Recent activity on this dataset")
        if ev:
            st.dataframe(pd.DataFrame(ev)[["timestamp_utc", "username", "user_role", "action_label", "resource"]].iloc[::-1].head(15),
                         width="stretch", hide_index=True)
        else:
            st.caption("No recorded activity yet.")
        st.caption("Viewing or acknowledging this information is oversight; it is not approval of repairs or certification "
                   "of pipeline safety.")
