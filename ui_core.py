"""CorroSight UI core: shared state, helpers, sidebar data controls and the original four pages.

Imported by app.py (entry point and navigation) and views.py (new pages). Every number on screen comes from
src.pipeline.run_analysis() on the loaded dataset.
"""

from __future__ import annotations

import json
import os
import sys
from html import escape
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src import __version__  # noqa: E402
from src import charts  # noqa: E402
from src import theme  # noqa: E402
from src import actions as ACT  # noqa: E402
from src import rbac  # noqa: E402
from src.audit import AuditLog  # noqa: E402
from src.rbac import PermissionDenied  # noqa: E402
from src.assessment import SCOPE_TABLE  # noqa: E402
from src.optimization import DEFAULT_ACTION_ASSUMPTIONS, plan  # noqa: E402
from src.pipeline import AnalysisResult, SourceInfo, attach_evaluation, available_runs, run_analysis  # noqa: E402
from src.prioritization import CATEGORIES, NEXT_STEP_OPTIONS  # noqa: E402
from src.reporting import build_pdf, findings_frame, to_csv_bytes  # noqa: E402
from src.review import WORKBENCH_STATUSES, ReviewStore  # noqa: E402
from src.anomalies import AnomalyConfig, CorrectionLog, detect as detect_anomalies  # noqa: E402
from src.conflicts import ResolutionLog  # noqa: E402
from src.contradictions import find as find_contradictions  # noqa: E402
from src.gaps import finding_gaps  # noqa: E402
from src.logstore import JsonLog  # noqa: E402
from src.model_arena import run_arena  # noqa: E402
from src.snapshots import SnapshotStore  # noqa: E402
from src.schema import COLUMN_DOCS, DEMO_ASSUMPTION_NOTE, REQUIRED_COLUMNS, AnalysisConfig  # noqa: E402
from src.synthetic_data import PIPELINE_LENGTH_M, write_demo_files  # noqa: E402
from src.validation import read_csv  # noqa: E402
from src.value_calculator import ValueInputs, calculate  # noqa: E402

DATA_DIR = ROOT / "data"
OUT_DIR = Path(os.environ.get("CORROSIGHT_OUTPUT_DIR", ROOT / "outputs"))
DEMO_FILE = DATA_DIR / "synthetic_inspections.csv"
GT_FILE = DATA_DIR / "synthetic_ground_truth.csv"
REVIEW_LOG = Path(os.environ.get("CORROSIGHT_REVIEW_LOG", OUT_DIR / "review_log.json"))
RESOLUTION_LOG = OUT_DIR / "identity_resolutions.json"
CORRECTION_LOG = OUT_DIR / "measurement_corrections.json"
SNAPSHOT_LOG = OUT_DIR / "analysis_snapshots.json"
EXPORT_LOG = OUT_DIR / "export_log.json"
AUDIT_LOG = Path(os.environ.get("CORROSIGHT_AUDIT_LOG", OUT_DIR / "audit_log.json"))


# ============================================================================ identity and permissions
def current_user() -> dict | None:
    """The signed-in account (re-read from the user store on every run by auth_ui.session_user)."""
    return st.session_state.get("auth_user")


def audit_log() -> AuditLog:
    return AuditLog(AUDIT_LOG)


def can(cap: str) -> bool:
    return rbac.can(current_user(), cap)


def deny_note(cap: str):
    st.caption(f":material/lock: {rbac.explain(cap)}")


def run_action(fn, *args, **kw):
    """Call a src.actions function as the current user; show the reason if it is refused."""
    try:
        return fn(current_user(), audit_log(), *args, **kw)
    except PermissionDenied as e:
        st.error(f"Not permitted. {e}")
    except ValueError as e:
        st.error(str(e))
    return None


# ============================================================================ helpers
def fmt(v, nd=2, unit="", na="-"):
    if v is None or (isinstance(v, (float, np.floating)) and np.isnan(v)):
        return na
    if isinstance(v, (float, np.floating)) and np.isinf(v):
        return "not reached"
    if isinstance(v, (float, np.floating, int, np.integer)):
        return f"{v:.{nd}f}{unit}"
    return f"{v}{unit}"


def kpi(col, label, value, sub="", hi=False):
    col.markdown(f"<div class='cs-kpi{' hi' if hi else ''}'><div class='l'>{label}</div><div class='v'>{value}</div>"
                 f"<div class='s'>{sub}</div></div>", unsafe_allow_html=True)


def cat_chip(cat):
    return f"<span class='cat' style='background:{charts.CAT_COLOURS.get(cat, theme.SLATE)}'>{cat}</span>"


def ensure_demo_files():
    if not DEMO_FILE.exists() or not GT_FILE.exists():
        write_demo_files(DATA_DIR)


@st.cache_resource(show_spinner=False, max_entries=6)
def cached_analysis(csv_text: str, source_json: str, cfg_json: str, run_a: str | None, run_b: str | None,
                    evaluate: bool) -> AnalysisResult:
    raw = read_csv(csv_text.encode("utf-8"))
    src = SourceInfo(**json.loads(source_json))
    cfg = AnalysisConfig(**json.loads(cfg_json))
    res = run_analysis(raw, src, cfg, run_a, run_b)
    if evaluate and res.ok and GT_FILE.exists():
        attach_evaluation(res, pd.read_csv(GT_FILE))   # post-hoc only; never an input to the analysis
    return res


def set_dataset(raw: pd.DataFrame, source: SourceInfo, evaluate: bool):
    st.session_state.raw_csv = raw.to_csv(index=False)
    st.session_state.source = asdict(source)
    st.session_state.evaluate = evaluate
    runs = available_runs(raw).dropna(subset=["inspection_date"])
    st.session_state.run_a = runs["run_id"].iloc[-2] if len(runs) >= 2 else None
    st.session_state.run_b = runs["run_id"].iloc[-1] if len(runs) >= 2 else None
    st.session_state.focus_track = None
    st.session_state.pop("pdf_bytes", None)


def load_demo():
    ensure_demo_files()
    raw = read_csv(DEMO_FILE)
    src = SourceInfo("Demo dataset (synthetic, fictional pipeline CG-DEMO-24IN-01)", [DEMO_FILE.name], True,
                     PIPELINE_LENGTH_M, ["Generated by src/synthetic_data.py (seeded, reproducible)."])
    set_dataset(raw, src, evaluate=True)


def load_demo_as_user() -> bool:
    if not can("load_shared_dataset"):
        st.error(rbac.explain("load_shared_dataset"))
        return False
    load_demo()
    res = get_result()
    run_action(ACT.load_dataset, False, "Demo dataset", [DEMO_FILE.name], res.fingerprint if res is not None else "")
    return True


def review_store() -> ReviewStore:
    return ReviewStore(REVIEW_LOG)


# Page registry filled by app.py on every run: key -> st.Page. Used for cross-page "open in ..." buttons.
NAV: dict = {}


def goto(page_key: str, track_id: str | None = None, **state):
    """Switch to another page, carrying the selected finding (and optional widget state) with it."""
    if track_id:
        st.session_state.focus_track = track_id
    for k, v in state.items():
        st.session_state[k] = v
    if page_key in NAV:
        st.switch_page(NAV[page_key])


def open_buttons(track_id: str, targets: list[tuple[str, str]], key: str):
    """Row of buttons that open the same finding on other pages."""
    cols = st.columns(len(targets))
    for c, (page_key, label) in zip(cols, targets):
        if c.button(label, key=f"{key}_{page_key}_{track_id}", width="stretch"):
            goto(page_key, track_id)


def resolution_log() -> ResolutionLog:
    return ResolutionLog(RESOLUTION_LOG)


def correction_log() -> CorrectionLog:
    return CorrectionLog(CORRECTION_LOG)


def snapshot_store() -> SnapshotStore:
    return SnapshotStore(SNAPSHOT_LOG)


def export_log() -> JsonLog:
    return JsonLog(EXPORT_LOG)


def log_export(res, kind: str, tracks, file: str, snapshot_id: str = ""):
    export_log().append(dict(dataset_fingerprint=res.fingerprint, kind=kind, tracks=tracks, file=file,
                             snapshot_id=snapshot_id or ""))


def latest_snapshot_id(res) -> str:
    snaps = snapshot_store().list(res.fingerprint)
    return snaps[-1]["snapshot_id"] if snaps else ""


def _memo(res, key: str, fn):
    """Cache derived results on the (cached) AnalysisResult object itself."""
    store = res.__dict__.setdefault("_derived", {})
    if key not in store:
        store[key] = fn()
    return store[key]


def anomaly_config() -> AnomalyConfig:
    return AnomalyConfig(**st.session_state.get("anomaly_cfg", AnomalyConfig().to_dict()))


def get_anomalies(res):
    cfg = anomaly_config()
    return _memo(res, f"anomalies-{cfg}", lambda: detect_anomalies(res, cfg))


def get_resolutions(res) -> dict:
    return resolution_log().latest_by(res.fingerprint, "track_id")


def get_contradictions(res):
    # depends on review / resolution logs, which can change between reruns, so it is recomputed (fast)
    return find_contradictions(res, review_store().history(res.fingerprint), get_resolutions(res))


def get_gaps(res):
    return _memo(res, "gaps-" + str(anomaly_config()), lambda: finding_gaps(res.findings, get_anomalies(res)))


def get_arena(res):
    if not (res.source.synthetic and GT_FILE.exists() and st.session_state.get("evaluate")):
        return None
    return _memo(res, "arena", lambda: run_arena(res.growth, pd.read_csv(GT_FILE), res.match.run_a, res.match.run_b,
                                                 res.config.noise_k))


def export_extras(res) -> dict:
    return dict(snapshot_id=latest_snapshot_id(res), anomalies=get_anomalies(res), contradictions=get_contradictions(res),
                gaps=get_gaps(res), resolutions=get_resolutions(res),
                corrections=correction_log().for_dataset(res.fingerprint), arena=get_arena(res))


def get_result() -> AnalysisResult | None:
    if "raw_csv" not in st.session_state:
        return None
    cfg = st.session_state.get("cfg", AnalysisConfig().to_dict())
    return cached_analysis(st.session_state.raw_csv, json.dumps(st.session_state.source), json.dumps(cfg),
                           st.session_state.get("run_a"), st.session_state.get("run_b"),
                           st.session_state.get("evaluate", False))


def focus_options(F: pd.DataFrame, mask=None) -> list[str]:
    sub = F if mask is None else F[mask]
    return sub["track_id"].tolist()


def finding_label(F: pd.DataFrame):
    lab = {r.track_id: f"{r.track_id} | {r.review_category} | {r.match_status_label} | "
                       f"{r.obs_a if isinstance(r.obs_a, str) else '-'} -> {r.obs_b if isinstance(r.obs_b, str) else '-'}"
           for r in F.itertuples()}
    return lambda t: lab.get(t, t)


def table_pick(ev, view: pd.DataFrame, col: str, key: str):
    """Apply a row selection from a dataframe only when it changes (so the selectbox can still override it)."""
    rows = list(ev.selection.rows) if ev and ev.selection else []
    if rows != st.session_state.get(f"_last_{key}"):
        st.session_state[f"_last_{key}"] = rows
        if rows:
            st.session_state.focus_track = view.iloc[rows[0]][col]


def pick_finding(F: pd.DataFrame, options: list[str], label: str, key: str, default: str | None = None):
    """Selectbox synchronised with the session-wide focus finding.

    The focus only changes when the user picks something (or selects a table row), so moving between
    screens keeps the finding the user is investigating.
    """
    if not options:
        st.info("No findings match the current filters.")
        return None
    cur = st.session_state.get("focus_track")
    start = cur if cur in options else (default if default in options else options[0])
    idx = options.index(start)
    choice = st.selectbox(label, options, index=idx, format_func=finding_label(F), key=f"{key}_{idx}_{len(options)}")
    if choice != start:
        st.session_state.focus_track = choice
    return choice


# ============================================================================ sidebar
def sidebar_controls():
    """Data source, run selection and settings. Rendered below the grouped page navigation."""
    with st.sidebar:
        st.markdown("<div class='cs-side-h'>Inspection data</div>", unsafe_allow_html=True)
        modes = ["Demo dataset"] + (["Upload CSV files"] if can("upload_data") else [])
        mode = st.radio("Data source", modes, horizontal=True, key="mode", label_visibility="collapsed")
        if not can("upload_data"):
            deny_note("upload_data")
        if mode == "Demo dataset":
            st.caption("Fictional 4.8 km pipeline, 40 segments, two runs (2016, 2023) with realistic data problems.")
            if st.button("Load demo dataset", type="primary", width="stretch", key="load_demo"):
                load_demo_as_user()
        else:
            upload_panel()

        if "raw_csv" in st.session_state:
            raw = read_csv(st.session_state.raw_csv.encode("utf-8"))
            runs = available_runs(raw).dropna(subset=["inspection_date"])
            if len(runs) >= 2:
                st.markdown("<div class='cs-side-h'>Runs to compare</div>", unsafe_allow_html=True)
                ids = runs["run_id"].tolist()
                lab = {r.run_id: f"{r.run_id} ({r.inspection_date:%Y-%m-%d}, {r.records} rec.)" for r in runs.itertuples()}
                a = st.selectbox("Earlier run", ids, index=ids.index(st.session_state.run_a) if st.session_state.get("run_a") in ids else len(ids) - 2,
                                 format_func=lab.get, key="sel_run_a")
                b = st.selectbox("Later run", ids, index=ids.index(st.session_state.run_b) if st.session_state.get("run_b") in ids else len(ids) - 1,
                                 format_func=lab.get, key="sel_run_b")
                if a == b:
                    st.error("Choose two different runs.")
                else:
                    st.session_state.run_a, st.session_state.run_b = a, b
            settings_panel()
        st.divider()
        src = st.session_state.get("source")
        badge = ("<span class='cs-chip syn'>SYNTHETIC DEMO DATA</span>" if src and src.get("synthetic")
                 else "<span class='cs-chip real'>USER DATA</span>" if src else "<span class='cs-chip real'>NO DATA LOADED</span>")
        st.markdown(f"<div class='cs-side-foot'><div class='cs-avatar'>CS</div><div>{badge}<br>"
                    f"v{__version__} &middot; decision-support prototype</div></div>", unsafe_allow_html=True)
        st.caption("Not a certified integrity assessment. Human approval is required for every consequential decision.")


def upload_panel():
    st.caption("Upload one CSV containing several runs, or one CSV per run. Required columns: "
               + ", ".join(REQUIRED_COLUMNS) + " (run_id / inspection_date can be entered below if absent).")
    files = st.file_uploader("Inspection CSV files", type=["csv"], accept_multiple_files=True, key="uploads")
    length = st.number_input("Pipeline length (m, optional, for range checks)", min_value=0.0, value=0.0, step=100.0,
                             key="up_len")
    frames, notes, problems = [], [], []
    for k, f in enumerate(files or []):
        try:
            df = read_csv(f.getvalue())
        except Exception as e:  # pragma: no cover - surfaced to the user
            problems.append(f"{f.name}: could not be read as CSV ({e}).")
            continue
        has_run = "run_id" in df.columns and df["run_id"].notna().all()
        has_date = "inspection_date" in df.columns and df["inspection_date"].notna().all()
        with st.expander(f"{f.name} - {len(df)} rows", expanded=not (has_run and has_date)):
            st.dataframe(df.head(5), width="stretch", hide_index=True)
            if not has_run:
                rid = st.text_input("Run ID for this file", value=Path(f.name).stem, key=f"rid_{k}")
                df["run_id"] = rid
                notes.append(f"run_id set to '{rid}' for every row of {f.name} by the user.")
            if not has_date:
                d = st.date_input("Inspection date for this file", value=date(2023, 1, 1), key=f"rdate_{k}")
                df["inspection_date"] = d.isoformat()
                notes.append(f"inspection_date set to {d.isoformat()} for every row of {f.name} by the user.")
        frames.append((f.name, df))
    for p in problems:
        st.error(p)
    if frames and st.button("Analyse uploaded data", type="primary", width="stretch", key="use_upload"):
        try:
            ACT.check(current_user(), audit_log(), "upload_data", "upload")
        except PermissionDenied as e:
            st.error(f"Not permitted. {e}")
            return
        raw = pd.concat([d for _, d in frames], ignore_index=True)
        src = SourceInfo("Uploaded inspection data", [n for n, _ in frames], False, length or None, notes)
        set_dataset(raw, src, evaluate=False)
        res = get_result()
        run_action(ACT.load_dataset, True, "Uploaded inspection data", [n for n, _ in frames],
                   res.fingerprint if res is not None else "")


def settings_panel():
    cur = AnalysisConfig(**st.session_state.get("cfg", AnalysisConfig().to_dict()))
    with st.expander("3 · Analysis settings (demo assumptions)"):
        with st.form("settings"):
            st.caption(DEMO_ASSUMPTION_NOTE)
            st.markdown("**Review rules**")
            depth = st.number_input("Depth review threshold (% WT)", 5.0, 95.0, cur.depth_review_pct_wt, 5.0)
            rate = st.number_input("Rate review threshold (mm/yr)", 0.01, 2.0, cur.rate_review_mm_per_yr, 0.05)
            thr = st.number_input("Screening threshold for projections (% WT)", 10.0, 95.0, cur.screening_threshold_pct_wt, 5.0)
            hor = st.number_input("Projection horizon (years after later run)", 1.0, 30.0, cur.forecast_horizon_years, 1.0)
            k = st.number_input("Noise test k (change > k x sigma)", 1.0, 4.0, cur.noise_k, 0.5)
            method = st.radio("Forecast method", ["baseline", "shrinkage"], index=0 if cur.forecast_method == "baseline" else 1,
                              horizontal=True, help="baseline = per-defect observed rate; shrinkage = empirical-Bayes model B")
            st.markdown("**Matching**")
            align = st.checkbox("Estimate per-segment odometer offset", cur.align_runs)
            pg = st.number_input("Axial gate (m)", 0.1, 5.0, cur.pos_gate_m, 0.1)
            cg = st.number_input("Clock gate (h)", 0.25, 6.0, cur.clock_gate_h, 0.25)
            am = st.number_input("Ambiguity margin (normalised distance)", 0.0, 5.0, cur.ambiguity_margin, 0.25)
            c1, c2 = st.columns(2)
            allowed = can("change_analysis_settings")
            apply = c1.form_submit_button("Apply", type="primary", disabled=not allowed)
            reset = c2.form_submit_button("Defaults", disabled=not allowed)
        if not allowed:
            deny_note("change_analysis_settings")
        new = None
        if apply:
            new = asdict(AnalysisConfig(
                depth_review_pct_wt=depth, rate_review_mm_per_yr=rate, screening_threshold_pct_wt=thr,
                forecast_horizon_years=hor, noise_k=k, forecast_method=method, align_runs=align, pos_gate_m=pg,
                clock_gate_h=cg, ambiguity_margin=am))
        if reset:
            new = AnalysisConfig().to_dict()
        if new is not None:
            res = get_result()
            if run_action(ACT.change_settings, asdict(cur), new, res.fingerprint if res is not None else "") is not None:
                st.session_state.cfg = new
                st.session_state.pop("pdf_bytes", None)
                st.rerun()


# ============================================================================ landing
def landing():
    topbar("Welcome", None)
    st.markdown("<div class='cs-splash'>" + theme.logo_html(64, "2.6rem") +
                "<div class='cs-splash-sub'>What changed between inspections, how reliable the evidence is, "
                "and what should be reviewed first - and why.</div></div>", unsafe_allow_html=True)
    st.markdown(flow_html(None), unsafe_allow_html=True)
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("Load demo dataset", type="primary", width="stretch", key="landing_demo"):
            if load_demo_as_user():
                st.rerun()
        st.caption("Or upload your own CSV files from the sidebar.")
    with c2:
        st.markdown("<div class='cs-banner'>Prototype for GCEM Hacks 5.0. The demo uses fictional synthetic data. "
                    "CorroSight does not certify safety, predict failures or prescribe repairs.</div>", unsafe_allow_html=True)
    st.markdown("##### Expected CSV schema")
    st.dataframe(schema_table(), width="stretch", hide_index=True)


def schema_table():
    return pd.DataFrame([dict(column=c, required="yes" if c in REQUIRED_COLUMNS else "optional", unit=u,
                              description=d, value_type=t) for c, (u, d, t) in COLUMN_DOCS.items()])


def flow_html(res: AnalysisResult | None):
    reviews = len(review_store().history(res.fingerprint)) if res is not None and res.ok else 0
    s = res.summary() if res is not None and res.ok else {}
    steps = [
        ("Load", "Inspection data", f"{s.get('n_records_a', 0) + s.get('n_records_b', 0)} records" if s else "demo or upload"),
        ("Validate", "Data quality", f"{s['issue_counts']['Error']} errors, {s['issue_counts']['Warning']} warnings" if s else "flag, never delete"),
        ("Match", "Memory Graph", f"{s['match_counts']['LIKELY_MATCH']} likely, {s['match_counts']['AMBIGUOUS']} ambiguous" if s else "one-to-one, explained"),
        ("Grow", "Change & forecast", f"{s['years_between']:.1f} yr between runs" if s else "observed vs predicted"),
        ("Prioritise", "Why-Inspect-First", f"{s['review_counts'].get('Review first', 0)} review first" if s else "explainable rules"),
        ("Review", "Human decision", f"{reviews} decision(s) logged" if s else "proposed vs recorded"),
        ("Export", "Evidence Passport", "PDF + CSV" if s else "traceable report"),
    ]
    html = "<div class='cs-flow'>"
    for i, (n, t, d) in enumerate(steps, 1):
        html += f"<div class='cs-step {'done' if s else ''}'><div class='n'>{i:02d} {n.upper()}</div><div class='t'>{t}</div><div class='d'>{d}</div></div>"
    return html + "</div>"


def topbar(title: str, synthetic: bool | None):
    chip = "" if synthetic is None else (
        "<span class='cs-chip syn'>SYNTHETIC DEMO DATA</span>" if synthetic else "<span class='cs-chip real'>USER DATA</span>")
    u = current_user()
    who = (f"<span class='cs-chip user'>{escape(u['display_name'])} &middot; {escape(rbac.ROLES[u['role']]['title'])}</span>"
           if u else "")
    st.markdown(f"<div class='cs-topbar'><div class='cs-search'>&#9906;&nbsp; Dashboard &nbsp;/&nbsp; <b>{title}</b></div>"
                f"<div style='display:flex;gap:.4rem;flex-wrap:wrap'>{chip}{who}</div></div>", unsafe_allow_html=True)


def header(res: AnalysisResult, title: str, desc: str | None = None):
    topbar(title, res.source.synthetic)
    st.markdown(f"## {title}")
    if desc:
        st.markdown(f"<div class='cs-desc'>{desc}</div>", unsafe_allow_html=True)
    src = res.source
    if src.synthetic:
        st.markdown("<div class='cs-banner'><b>SYNTHETIC DEMO DATA.</b> Fictional pipeline generated for demonstration. "
                    "Results do not describe any real asset.</div>", unsafe_allow_html=True)
    if res.ok:
        s = res.summary()
        st.caption(f"{src.name} · {s['run_a']} ({s['date_a']}) → {s['run_b']} ({s['date_b']}), {s['years_between']:.2f} yr · "
                   f"forecast method: {res.config.forecast_method} · dataset SHA-256 {res.fingerprint[:12]}…")


# ============================================================================ page 1
def page_overview(res: AnalysisResult):
    header(res, "Pipeline Overview")
    if not res.ok:
        st.error("The analysis cannot run with this data. See the blocking issues below.")
        st.dataframe(res.issues, width="stretch", hide_index=True)
        return
    s = res.summary()
    F = res.findings
    st.markdown(flow_html(res), unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["Summary", "Inspection data & validation"])
    with tab1:
        c = st.columns(6)
        kpi(c[0], "Runs compared", f"<span style='font-size:1.15rem'>{s['run_a']} → {s['run_b']}</span>",
            f"{s['years_between']:.2f} years apart")
        kpi(c[1], "Segments", s["n_segments"], ", ".join(s["pipeline_ids"]))
        kpi(c[2], "Observations", s["n_records_a"] + s["n_records_b"], f"{s['n_records_a']} earlier · {s['n_records_b']} later")
        kpi(c[3], "Findings (tracks)", s["n_findings"], "one per suspected defect / record")
        kpi(c[4], "Data-quality issues", s["issue_counts"]["Error"] + s["issue_counts"]["Warning"],
            f"{s['issue_counts']['Error']} errors · {s['issue_counts']['Warning']} warnings")
        kpi(c[5], "Review first", s["review_counts"].get("Review first", 0), "explainable demo rules", hi=True)
        st.write("")
        mc = s["match_counts"]
        c = st.columns(5)
        kpi(c[0], "Likely matches", mc["LIKELY_MATCH"], "one-to-one, unambiguous", hi=True)
        kpi(c[1], "Ambiguous", mc["AMBIGUOUS"], "provisional, needs verification")
        kpi(c[2], "Not found later", mc["UNMATCHED_EARLIER"], "earlier record, no partner")
        kpi(c[3], "New in later run", mc["NEW_LATER"], "no earlier partner")
        kpi(c[4], "Excluded", mc["EXCLUDED"], "duplicates / invalid location")
        st.write("")
        c1, c2 = st.columns(2)
        c1.plotly_chart(charts.category_bar(F), width="stretch", key="ov_cat")
        c2.plotly_chart(charts.match_bar(F), width="stretch", key="ov_match")
        st.plotly_chart(charts.pipeline_strip(F, res.source.pipeline_length_m), width="stretch", key="ov_strip")
        st.markdown("##### Top findings for review")
        rv = review_store().latest(res.fingerprint)
        st.markdown("".join(priority_row(r, rv, None) for r in F[F["review_rank"] <= 2].head(6).itertuples()),
                    unsafe_allow_html=True)
        st.caption("Review priority is a recommendation for human review, not a risk score or failure probability.")
    with tab2:
        validation_tab(res)


def validation_tab(res: AnalysisResult):
    v = res.validation
    d = v.data
    c = st.columns(4)
    cnt = res.summary()["issue_counts"]
    kpi(c[0], "Errors", cnt["Error"], "record excluded from the affected calculation")
    kpi(c[1], "Warnings", cnt["Warning"], "flagged, kept, may raise priority")
    kpi(c[2], "Info", cnt["Info"], "context for interpretation")
    kpi(c[3], "Records retained", f"{len(d)} / {len(d)}", "nothing deleted or rescaled")
    st.write("")
    st.markdown("##### Issues found - what, effect, and what you can do")
    sev = st.multiselect("Severity", ["Error", "Warning", "Info"], default=["Error", "Warning", "Info"], key="val_sev")
    codes = sorted(res.issues["code"].unique())
    code_f = st.multiselect("Issue type", codes, default=codes, key="val_codes")
    iss = res.issues[res.issues["severity"].isin(sev) & res.issues["code"].isin(code_f)]
    st.dataframe(iss, width="stretch", hide_index=True, height=300)
    if v.log:
        st.markdown("##### Transformation / exclusion log")
        for line in v.log + [f"Source note: {n}" for n in res.source.notes]:
            st.markdown(f"- {line}")
    st.markdown("##### Record preview (source values + validation flags)")
    c1, c2, c3 = st.columns([1, 1, 2])
    run_f = c1.selectbox("Run", ["All"] + sorted(d["run_id"].dropna().unique().tolist()), key="prev_run")
    only = c2.checkbox("Only flagged records", key="prev_flag")
    q = c3.text_input("Search observation ID", key="prev_q")
    view = d.copy()
    if run_f != "All":
        view = view[view["run_id"] == run_f]
    if only:
        view = view[view["quality_flags"].str.len() > 0]
    if q:
        view = view[view["observation_id"].astype(str).str.contains(q, case=False)]
    cols = ["source_row", "run_id", "inspection_date", "observation_id", "segment_id", "joint_id", "axial_position_m",
            "clock_position_h", "depth_mm", "length_mm", "width_mm", "nominal_wt_mm", "depth_uncertainty_mm",
            "depth_pct_wt", "quality_flags", "match_eligible", "exclusion_reason"]
    st.dataframe(view[cols], width="stretch", hide_index=True, height=360,
                 column_config={"depth_pct_wt": st.column_config.NumberColumn("depth % WT", format="%.1f")})
    st.caption(f"{len(view)} of {len(d)} records shown. source_row = line number in the uploaded CSV.")
    with st.expander("Schema and units"):
        st.dataframe(schema_table(), width="stretch", hide_index=True)


# ============================================================================ page 2
def page_history(res: AnalysisResult):
    header(res, "Defect History · Corrosion Memory Graph")
    if not res.ok:
        st.warning("Load valid data with two inspection runs first.")
        return
    F, m = res.findings, res.match
    st.caption("Each finding is a suspected physical defect tracked across the two runs. Uncertain links stay uncertain: "
               "ambiguous pairs are shown as provisional and unmatched records are never forced into a match.")
    c1, c2, c3 = st.columns([2, 2, 1])
    segs = sorted(F["segment_id"].dropna().unique())
    seg = c1.selectbox("Segment window", segs, index=0, key="hist_seg")
    statuses = list(charts.MATCH_COLOURS)
    st_f = c2.multiselect("Match status", statuses, default=statuses, key="hist_status")
    show_all = c3.checkbox("All segments in table", key="hist_all")
    seg_rows = F[F["segment_id"] == seg]
    pos = pd.concat([seg_rows["pos_a"], seg_rows["pos_b"]]).dropna()
    lo, hi = (float(pos.min()) - 2, float(pos.max()) + 2) if len(pos) else (0.0, 120.0)
    focus = st.session_state.get("focus_track")
    fig = charts.memory_graph(F[F["match_status_label"].isin(st_f)], m.candidates, (lo, hi), focus, m.run_a, m.run_b)
    st.plotly_chart(fig, width="stretch", key="mem_graph")
    off = m.offsets.set_index("segment_id")
    if seg in off.index:
        o = off.loc[seg]
        st.caption(f"Segment {seg}: odometer offset {o['offset_m']:+.3f} m applied to later-run positions for matching "
                   f"({o['source']}, {int(o['n_anchor_pairs'])} anchor pairs). Reported positions are unchanged.")
    table = F if show_all else F[F["segment_id"] == seg]
    table = table[table["match_status_label"].isin(st_f)]
    cols = {"track_id": "finding", "match_status_label": "match status", "obs_a": f"{m.run_a} obs", "obs_b": f"{m.run_b} obs",
            "pos_a": f"{m.run_a} pos m", "pos_b": f"{m.run_b} pos m", "d_pos_raw_m": "raw Δpos m",
            "d_pos_aligned_m": "aligned Δpos m", "d_clock_h": "Δclock h", "distance": "match distance",
            "agreement": "agreement index", "n_alternatives": "competing", "depth_a": f"{m.run_a} depth mm",
            "depth_b": f"{m.run_b} depth mm", "delta_mm": "Δdepth mm", "review_category": "review category"}
    tv = table[list(cols)].rename(columns=cols)
    st.markdown(f"##### Tracks ({len(tv)}) - select a row to open its evidence")
    ev = st.dataframe(tv, width="stretch", hide_index=True, height=300, on_select="rerun",
                      selection_mode="single-row", key=f"hist_tbl_{seg}_{show_all}",
                      column_config={c: st.column_config.NumberColumn(format="%.3f") for c in
                                     ["raw Δpos m", "aligned Δpos m", "Δclock h", "match distance", "agreement index", "Δdepth mm"]})
    table_pick(ev, tv, "finding", f"hist_tbl_{seg}_{show_all}")
    st.caption("Agreement index = exp(-d²/2): 1.0 means identical aligned location and size. It is a similarity measure, "
               "not a probability that the match is correct.")
    st.divider()
    tid = pick_finding(F, table["track_id"].tolist() or F["track_id"].tolist(), "Open finding", "hist_pick")
    if tid:
        finding_evidence(res, tid)


def finding_evidence(res: AnalysisResult, tid: str, show_title: bool = True):
    F, m = res.findings.set_index("track_id"), res.match
    g = F.loc[tid]
    d = res.validation.data
    if show_title:
        st.markdown(f"### {tid} &nbsp; {cat_chip(g['review_category'])}", unsafe_allow_html=True)
    st.markdown(f"<div class='cs-card accent'><h4>Match decision: {g['match_status_label']}</h4><p>{g['rationale']}</p>"
                + (f"<p class='muted'>Competing candidates: {g['alternatives']}</p>" if g["alternatives"] else "")
                + "</div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    for col, run, obs, date_ in ((c1, m.run_a, g["obs_a"], m.date_a), (c2, m.run_b, g["obs_b"], m.date_b)):
        with col:
            st.markdown(f"<span class='tag t-obs'>OBSERVED</span> **{run}** · {date_:%Y-%m-%d}", unsafe_allow_html=True)
            if isinstance(obs, str):
                rec = d[(d["run_id"] == run) & (d["observation_id"] == obs)]
                show = ["source_row", "observation_id", "segment_id", "joint_id", "axial_position_m", "clock_position_h",
                        "depth_mm", "length_mm", "width_mm", "nominal_wt_mm", "depth_uncertainty_mm", "quality_flags"]
                st.dataframe(rec[show].T.rename(columns=lambda _: "value").astype(str), width="stretch")
            else:
                st.info("No observation in this run for this finding.")
    if g["match_status"] in ("LIKELY_MATCH", "AMBIGUOUS") and np.isfinite(g["delta_mm"]):
        st.markdown(f"<span class='tag t-calc'>CALCULATED</span> change {g['delta_mm']:+.2f} mm over {g['dt_years']:.2f} yr "
                    f"= {g['rate_mm_per_yr']:+.3f} mm/yr · {g['change_class_label']}", unsafe_allow_html=True)
    cand = m.candidates
    if len(cand):
        cc = cand[(cand["obs_a"] == g["obs_a"]) | (cand["obs_b"] == g["obs_b"])]
        if len(cc):
            st.markdown("**All candidate pairs considered for this finding**")
            st.dataframe(cc[["obs_a", "obs_b", "d_pos_raw_m", "offset_m", "d_pos_aligned_m", "d_clock_h", "d_length_mm",
                             "distance", "assigned"]].round(3), width="stretch", hide_index=True)


# ============================================================================ page 3
def page_forecast(res: AnalysisResult):
    header(res, "Forecast & Priorities")
    if not res.ok:
        st.warning("Load valid data with two inspection runs first.")
        return
    t1, t2, t3 = st.tabs(["Why-Inspect-First", "Forecast & Honest AI", "Engineering readiness"])
    with t1:
        priorities_tab(res)
    with t2:
        forecast_tab(res)
    with t3:
        readiness_tab(res)


REASON_TITLES = {"C1": "Significant measured metal loss", "C2": "Upper scenario reaches demo threshold",
                 "C3": "Growth beyond measurement noise", "C4": "Apparent growth", "C5": "New detection, no history",
                 "E1": "Match unresolved", "E2": "Anomalous decrease", "E3": "Implausible change",
                 "E4": "Not found in later run", "E5": "Possible duplicate", "E6": "Wall-thickness conflict",
                 "E7": "Insufficient data", "E8": "Insufficient data", "E9": "Insufficient data", "E10": "Single observation"}


def priority_row(r, reviews: dict, focus: str | None) -> str:
    """One row of the reference-style priority list (finding | category | explainable result)."""
    first = str(r.priority_explanation).split(" | ")[0]
    code = first.split(":")[0].split(" ")[0]
    title = REASON_TITLES.get(code, "No review rule triggered")
    body = first.split(": ", 1)[1] if ": " in first and code in REASON_TITLES else first
    more = len(str(r.priority_explanation).split(" | ")) - 1
    obs = f"{r.obs_a if isinstance(r.obs_a, str) else '-'} &rarr; {r.obs_b if isinstance(r.obs_b, str) else '-'}"
    status = reviews.get(r.track_id, {}).get("status", "Not reviewed")
    return (f"<div class='cs-prow{' sel' if r.track_id == focus else ''}'>"
            f"<div><div class='t'>{r.track_id} &middot; segment {r.segment_id}<span class='pill'>{r.match_status_label}</span></div>"
            f"<div class='m'>{obs} &middot; latest {fmt(r.latest_pct_wt, 1, '% WT', na='% WT n/a')} &middot; "
            f"rate {fmt(r.rate_mm_per_yr, 3, ' mm/yr')}</div><div class='m'>{r.condition_level} condition &middot; "
            f"{r.evidence_quality} evidence &middot; {status}</div></div>"
            f"<div style='display:flex;align-items:center'>{cat_chip(r.review_category)}</div>"
            f"<div class='why'><span class='ne'>NOT A RISK SCORE</span><h5>{escape(title)}</h5><p>{escape(body)}"
            f"{f' (+{more} more)' if more else ''}</p></div></div>")


def priorities_tab(res: AnalysisResult):
    F = res.findings
    cfg = res.config
    st.caption("Category = the higher of the condition-based and evidence-based categories, so missing or uncertain "
               "evidence can only raise a finding. " + DEMO_ASSUMPTION_NOTE)
    c = st.columns(4)
    cats = c[0].multiselect("Review category", list(CATEGORIES.values()), default=list(CATEGORIES.values()), key="pr_cat")
    segs = c[1].multiselect("Segment", sorted(F["segment_id"].dropna().unique()), key="pr_seg", placeholder="All segments")
    ms = c[2].multiselect("Match status", list(charts.MATCH_COLOURS), key="pr_ms", placeholder="All statuses")
    eq = c[3].multiselect("Evidence quality", ["Adequate", "Limited", "Insufficient"], key="pr_eq", placeholder="All")
    sort_by = st.radio("Sort by", ["Review priority", "Latest % WT", "Observed rate", "Upper-scenario % WT"],
                       horizontal=True, key="pr_sort")
    sub = F[F["review_category"].isin(cats)]
    if segs:
        sub = sub[sub["segment_id"].isin(segs)]
    if ms:
        sub = sub[sub["match_status_label"].isin(ms)]
    if eq:
        sub = sub[sub["evidence_quality"].isin(eq)]
    key = {"Review priority": ("priority_order", True), "Latest % WT": ("latest_pct_wt", False),
           "Observed rate": ("rate_mm_per_yr", False), "Upper-scenario % WT": ("proj_pct_upper", False)}[sort_by]
    sub = sub.sort_values(key[0], ascending=key[1], na_position="last")
    reviews = review_store().latest(res.fingerprint)
    view = pd.DataFrame({
        "#": sub["priority_order"], "finding": sub["track_id"], "category": sub["review_category"],
        "condition": sub["condition_level"], "evidence": sub["evidence_quality"], "match": sub["match_status_label"],
        "segment": sub["segment_id"], "latest % WT": sub["latest_pct_wt"], "rate mm/yr": sub["rate_mm_per_yr"],
        "upper % WT @H": sub["proj_pct_upper"], "proposed next step": sub["proposed_next_step"],
        "review status": [reviews.get(t, {}).get("status", "Not reviewed") for t in sub["track_id"]],
        "why (first reason)": sub["priority_explanation"].str.split(" \\| ").str[0]})
    c1, c2 = st.columns([3, 1])
    c1.markdown(f"##### Defects listed by review priority ({len(view)})")
    layout = c2.radio("View", ["Explainable list", "Table"], horizontal=True, key="pr_view", label_visibility="collapsed")
    if layout == "Table":
        ev = st.dataframe(view, width="stretch", hide_index=True, height=360, on_select="rerun",
                          selection_mode="single-row", key="pr_tbl",
                          column_config={"latest % WT": st.column_config.NumberColumn(format="%.1f"),
                                         "rate mm/yr": st.column_config.NumberColumn(format="%.3f"),
                                         "upper % WT @H": st.column_config.NumberColumn(format="%.1f")})
        table_pick(ev, view, "finding", "pr_tbl")
    else:
        n = st.slider("Findings shown", 5, max(5, min(60, len(sub))), min(10, max(5, len(sub))), key="pr_n") if len(sub) > 5 else len(sub)
        st.markdown("".join(priority_row(r, reviews, st.session_state.get("focus_track")) for r in sub.head(n).itertuples()),
                    unsafe_allow_html=True)
        st.caption("Each row: finding and source records | review category | the first reason behind it. "
                   "Use 'Open finding' below for the full explanation. Review priority is not a risk score or failure probability.")
    tid = pick_finding(F, sub["track_id"].tolist(), "Open finding", "pr_pick")
    if not tid:
        return
    g = F.set_index("track_id").loc[tid]
    st.markdown(f"### {tid} &nbsp; {cat_chip(g['review_category'])}", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        items = "".join(f"<li>{x}</li>" for x in g["condition_reasons"].split(" | "))
        st.markdown(f"<div class='cs-card'><h4>Condition indicators: {g['condition_level']}</h4><ul>{items}</ul>"
                    "<p class='muted'>What the measurements suggest under the demo rules.</p></div>", unsafe_allow_html=True)
    with c2:
        items = "".join(f"<li>{x}</li>" for x in g["evidence_reasons"].split(" | "))
        st.markdown(f"<div class='cs-card'><h4>Evidence quality: {g['evidence_quality']}</h4><ul>{items}</ul>"
                    "<p class='muted'>How far the evidence can be trusted. Poor evidence is a reason to review, not to relax.</p></div>",
                    unsafe_allow_html=True)
    st.markdown(f"<div class='cs-card accent'><h4>Proposed next step (system suggestion, not an approval)</h4><p><b>{g['proposed_next_step']}</b></p>"
                f"<p>Missing inputs: {g['missing_inputs'] or 'none identified'} · Engineering readiness: {g['readiness_label']}</p>"
                f"<p class='muted'>Source records: {g['obs_a'] if isinstance(g['obs_a'], str) else '-'} ({res.match.run_a}) → "
                f"{g['obs_b'] if isinstance(g['obs_b'], str) else '-'} ({res.match.run_b}). Rules: depth ≥ {cfg.depth_review_pct_wt:g}% WT, "
                f"rate ≥ {cfg.rate_review_mm_per_yr:g} mm/yr beyond {cfg.noise_k:g}σ, upper scenario ≥ {cfg.screening_threshold_pct_wt:g}% WT "
                f"within {cfg.forecast_horizon_years:g} yr.</p></div>", unsafe_allow_html=True)
    with st.expander("Record a human review for this finding", expanded=False):
        review_form(res, tid, "pr")


def forecast_tab(res: AnalysisResult):
    F, cfg, m = res.findings, res.config, res.match
    paired = F[F["match_status"].isin(["LIKELY_MATCH", "AMBIGUOUS"])]
    c1, c2 = st.columns([3, 1])
    with c2:
        only_proj = st.checkbox("Only findings with a projection", value=False, key="fc_only")
    opts = paired[paired["forecast_status"] != "NOT_ESTABLISHED"] if only_proj else F
    projected = F[(F["forecast_status"] == "CENTRAL_AND_UPPER") & F["wt_mm"].notna()]["track_id"]
    with c1:
        tid = pick_finding(F, opts["track_id"].tolist(), "Finding", "fc_pick",
                           default=projected.iloc[0] if len(projected) else None)
    if not tid:
        return
    g = F.set_index("track_id").loc[tid]
    k = cfg.noise_k
    st.markdown(f"### {tid} &nbsp; {cat_chip(g['review_category'])} &nbsp; <span class='muted'>{g['match_status_label']}</span>",
                unsafe_allow_html=True)
    a, b, c, d = st.columns(4)
    with a:
        st.markdown(f"<div class='cs-card'><span class='tag t-obs'>OBSERVED</span><h4>Measurements</h4>"
                    f"<p>{m.run_a}: {fmt(g['depth_a'])} mm (±{fmt(g['u_a'])} 1σ)</p>"
                    f"<p>{m.run_b}: {fmt(g['depth_b'])} mm (±{fmt(g['u_b'])} 1σ)</p>"
                    f"<p>Nominal WT: {fmt(g['wt_mm'], 1, ' mm', na='MISSING')} (design)</p></div>", unsafe_allow_html=True)
    with b:
        st.markdown(f"<div class='cs-card'><span class='tag t-calc'>CALCULATED</span><h4>Arithmetic from measurements</h4>"
                    f"<p>Change: {fmt(g['delta_mm'], 2, ' mm')} over {fmt(g['dt_years'], 2, ' yr')}</p>"
                    f"<p>Annualised: {fmt(g['rate_mm_per_yr'], 3, ' mm/yr')}</p>"
                    f"<p>Latest depth: {fmt(g['latest_pct_wt'], 1, '% WT', na='n/a (WT missing)')}</p></div>", unsafe_allow_html=True)
    with c:
        if g["forecast_status"] == "NOT_ESTABLISHED":
            body = "<p><b>A reliable forecast cannot be established from the available data.</b></p>"
        else:
            body = (f"<p>Basis: {g['forecast_basis']}</p>"
                    f"<p>Central @+{cfg.forecast_horizon_years:g} yr: {fmt(g['proj_depth_central_mm'], 2, ' mm')} "
                    f"({fmt(g['proj_pct_central'], 1, '% WT', na='% WT n/a')})</p>"
                    f"<p>Upper scenario: {fmt(g['proj_depth_upper_mm'], 2, ' mm')} ({fmt(g['proj_pct_upper'], 1, '% WT', na='% WT n/a')})</p>"
                    f"<p>Years to demo {cfg.screening_threshold_pct_wt:g}% WT (upper): "
                    f"{'already at or above it' if g['yrs_to_threshold_upper'] == 0 else fmt(g['yrs_to_threshold_upper'], 1, na='n/a')}</p>")
        st.markdown(f"<div class='cs-card'><span class='tag t-pred'>PREDICTED · ILLUSTRATIVE</span><h4>{g['forecast_status_label']}</h4>"
                    f"{body}</div>", unsafe_allow_html=True)
    with d:
        unc = (f"<p>Measurement σ of rate: {fmt(g['sigma_rate_mm_per_yr'], 3, ' mm/yr')}</p>"
               f"<p>{k:g}σ range: {fmt(g['rate_low'], 3)} to {fmt(g['rate_high'], 3)} mm/yr</p>"
               f"<p>{g['change_class_label']}</p>") if np.isfinite(g["sigma_rate_mm_per_yr"]) else \
            "<p><b>No interval:</b> measurement uncertainty unknown or no paired change.</p>"
        st.markdown(f"<div class='cs-card'><span class='tag t-unc'>UNCERTAIN</span><h4>What the evidence cannot establish</h4>{unc}"
                    "<p class='muted'>Interval = measurement noise only. Matching, tool bias and non-constant growth are not included. "
                    "Two observations cannot establish a long-term trend.</p></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='cs-card'><span class='tag t-miss'>LIMITATION</span> {g['forecast_reason']}</div>", unsafe_allow_html=True)
    st.plotly_chart(charts.growth_chart(g, m.date_a, m.date_b, k, cfg.forecast_horizon_years, cfg.screening_threshold_pct_wt),
                    width="stretch", key="fc_chart")
    st.caption("Time to a demo screening threshold is an illustrative scenario, not a repair deadline or remaining life.")
    st.divider()
    st.markdown("#### Population view and model evaluation")
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.rate_histogram(res.growth), width="stretch", key="fc_hist")
    c2.plotly_chart(charts.shrinkage_scatter(res.growth), width="stretch", key="fc_shr")
    sh = res.shrinkage
    if sh and sh.fitted:
        st.caption(f"Model B (empirical-Bayes shrinkage) fitted on {sh.n} likely matches with known uncertainty: population mean "
                   f"{sh.mu:.4f} mm/yr, between-defect variance τ² = {sh.tau2:.5f}. Switch method in Analysis settings.")
    if res.evaluation and res.source.synthetic:
        eg, em = res.evaluation["growth"], res.evaluation["matching"]
        st.markdown("##### Evaluation against hidden synthetic ground truth")
        st.markdown("<div class='cs-banner'>Computed after the analysis from a separate ground-truth file that the analysis never reads. "
                    "Synthetic performance does not establish real-world accuracy; synthetic noise matches the stated uncertainty by "
                    "construction, so interval coverage is optimistic.</div>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.dataframe(pd.DataFrame([
                dict(metric="Likely-match precision", value=f"{em['likely']['precision']:.3f}", detail=f"{em['likely']['correct']}/{em['likely']['predicted_pairs']}"),
                dict(metric="Ambiguous-pair precision", value=f"{em['ambiguous']['precision']:.3f}", detail=f"{em['ambiguous']['correct']}/{em['ambiguous']['predicted_pairs']}"),
                dict(metric="Recall (likely + ambiguous)", value=f"{em['recall_all_assigned']:.3f}", detail=f"of {em['true_pairs']} true pairs"),
                dict(metric="Recall (likely only)", value=f"{em['recall_likely_only']:.3f}", detail="ambiguous held back for review"),
                dict(metric="False matches / missed pairs", value=f"{em['all_assigned']['false_matches']} / {em['missed_true_pairs']}", detail=""),
                dict(metric="'New in later run' truly new", value=f"{em['new_later']['precision']:.3f}", detail=f"n={em['new_later']['count']}"),
            ]), width="stretch", hide_index=True)
        with c2:
            if eg.get("n"):
                st.dataframe(pd.DataFrame([
                    dict(estimator="Baseline observed rate", MAE=round(eg["baseline"]["mae"], 4), RMSE=round(eg["baseline"]["rmse"], 4),
                         bias=round(eg["baseline"]["bias"], 4), coverage=round(eg["baseline_interval_coverage"], 3)),
                    dict(estimator="Model B shrinkage", MAE=round(eg["shrinkage"]["mae"], 4), RMSE=round(eg["shrinkage"]["rmse"], 4),
                         bias=round(eg["shrinkage"]["bias"], 4), coverage=round(eg["shrinkage_interval_coverage"], 3)),
                ]), width="stretch", hide_index=True)
                st.caption(f"Rate error in mm/yr on {eg['n']} correctly matched likely pairs; coverage = share of true rates "
                           f"inside the {eg['k']:g}σ interval. Lower RMSE on this synthetic data: {eg['better_model']}.")


def readiness_tab(res: AnalysisResult):
    F = res.findings
    s = res.summary()["readiness"]
    st.markdown("<div class='cs-banner'>CorroSight does <b>not</b> perform a remaining-strength assessment (e.g. the ASME B31G family), "
                "compute failure pressures or estimate failure probability, and claims no standards compliance. This screen shows "
                "whether a qualified engineer has the inputs to choose and run such an assessment.</div>", unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(SCOPE_TABLE, columns=["Question", "Status in CorroSight", "Explanation"]),
                 width="stretch", hide_index=True)
    c = st.columns(3)
    kpi(c[0], "Inputs missing", s["counts"]["MISSING_INPUTS"], "not ready for an engineering assessment")
    kpi(c[1], "Verification required", s["counts"]["VERIFY"], "inputs present, evidence to verify")
    kpi(c[2], "Inputs present", s["counts"]["INPUTS_PRESENT"], "assessment NOT performed here")
    st.plotly_chart(charts.missing_inputs_bar(s["most_common_missing"]), width="stretch", key="rd_bar")
    flt = st.multiselect("Readiness", sorted(F["readiness_label"].unique()), key="rd_f", placeholder="All")
    sub = F if not flt else F[F["readiness_label"].isin(flt)]
    st.dataframe(sub[["track_id", "review_category", "readiness_label", "inputs_available", "inputs_missing",
                      "requires_verification"]].rename(columns={"track_id": "finding"}),
                 width="stretch", hide_index=True, height=360)


# ============================================================================ page 4
def review_form(res: AnalysisResult, tid: str, prefix: str):
    store = review_store()
    g = res.findings.set_index("track_id").loc[tid]
    latest = store.latest(res.fingerprint).get(tid)
    proposed = g["proposed_next_step"]
    default_step = latest["reviewer_selected_next_step"] if latest else \
        ("Request missing inputs" if proposed.startswith("Request missing inputs") else proposed)
    options = NEXT_STEP_OPTIONS + (["Request missing inputs"] if "Request missing inputs" not in NEXT_STEP_OPTIONS else [])
    st.markdown(f"System-proposed next step: **{proposed}**  \n<span class='muted'>A proposal only. Recording a decision does not "
                "approve repairs, work orders or operating changes.</span>", unsafe_allow_html=True)
    statuses = list(WORKBENCH_STATUSES)
    if latest and latest["status"] not in statuses:
        statuses.append(latest["status"])           # legacy status from an older log stays selectable
    with st.form(f"{prefix}_review_{tid}"):
        c1, c2 = st.columns(2)
        status = c1.selectbox("Review status", statuses, index=statuses.index(latest["status"]) if latest else 0,
                              help="'Closed with Documented Rationale' requires a reason. No status means 'repaired'.")
        step = c2.selectbox("Reviewer-selected next step", options,
                            index=options.index(default_step) if default_step in options else 0)
        assignee = c1.text_input("Assigned to (optional)", value=latest.get("assigned_to", "") if latest else "")
        u = current_user()
        c2.markdown(f"<div class='muted' style='padding-top:1.9rem'>Recorded as <b>{escape(u['display_name']) if u else '-'}</b>"
                    f" ({escape(rbac.ROLES[u['role']]['title']) if u else '-'})</div>", unsafe_allow_html=True)
        reason = c1.text_area("Reason for this decision", value="", height=80)
        notes = c2.text_area("Notes", value="", height=80)
        allowed = can("record_review")
        ok = st.form_submit_button("Record review decision", type="primary", disabled=not allowed)
    if not allowed:
        deny_note("record_review")
    if ok:
        e = run_action(ACT.record_review, store, res.fingerprint, tid, status, step, proposed, notes, reason=reason,
                       assigned_to=assignee, snapshot_id=latest_snapshot_id(res))
        if e is not None:
            st.session_state.pop("pdf_bytes", None)
            st.success(f"Recorded for {tid} at {e['timestamp_utc']}: {status} (by {e['reviewer']}).")
    hist = store.history(res.fingerprint, tid)
    if hist:
        H = pd.DataFrame(hist)
        cols = [c for c in ["timestamp_utc", "status", "action", "reviewer", "user_role", "assigned_to", "reason", "system_proposed_next_step",
                            "reviewer_selected_next_step", "notes"] if c in H.columns]
        st.dataframe(H[cols].iloc[::-1], width="stretch", hide_index=True)


def page_evidence(res: AnalysisResult):
    header(res, "Evidence & Planning")
    if not res.ok:
        st.warning("Load valid data with two inspection runs first.")
        return
    t1, t2, t3, t4 = st.tabs(["Human review", "Evidence Passport (PDF / CSV)", "Business value", "Budget planner"])
    with t1:
        F = res.findings
        st.caption("Evidence → analysis → recommendation → human decision → Evidence Passport. Decisions are stored in "
                   "outputs/review_log.json and persist when the app is reopened.")
        only = st.checkbox("Only findings above Routine review", value=True, key="rv_only")
        opts = F[F["review_rank"] <= 4]["track_id"].tolist() if only else F["track_id"].tolist()
        tid = pick_finding(F, opts, "Finding to review", "rv_pick")
        if tid:
            g = F.set_index("track_id").loc[tid]
            st.markdown(f"{cat_chip(g['review_category'])} &nbsp; {g['priority_explanation']}", unsafe_allow_html=True)
            review_form(res, tid, "rv")
        hist = review_store().history(res.fingerprint)
        st.markdown(f"##### Review log for this dataset ({len(hist)} entries)")
        if hist:
            st.dataframe(pd.DataFrame(hist).drop(columns=["dataset_fingerprint", "approval_note"]).iloc[::-1],
                         width="stretch", hide_index=True)
    with t2:
        passport_tab(res)
    with t3:
        value_tab(res)
    with t4:
        planner_tab(res)


def passport_tab(res: AnalysisResult):
    store = review_store()
    latest = store.latest(res.fingerprint)
    extras = export_extras(res)
    table = findings_frame(res, latest, extras)
    st.markdown("The PDF and CSV are generated from the same analysis object and the same findings table shown below. "
                f"Analysis snapshot: **{extras['snapshot_id'] or 'none saved yet (save one under Reproducible Analysis Snapshots)'}**. "
                "The Evidence Passport records analysis and review evidence; it does not certify pipeline safety.")
    c1, c2 = st.columns([2, 1])
    with c1:
        mode = st.radio("Finding evidence sheets in the PDF", ["Top findings by priority", "Choose findings"], horizontal=True,
                        key="pp_mode")
        if mode == "Top findings by priority":
            n = st.slider("Number of evidence sheets", 1, 40, 10, key="pp_n")
            ids = table["finding_id"].head(n).tolist()
        else:
            ids = st.multiselect("Findings", table["finding_id"].tolist(),
                                 default=[st.session_state.focus_track] if st.session_state.get("focus_track") else [],
                                 format_func=finding_label(res.findings), key="pp_ids")
        inc_plan = st.checkbox("Include the current budget-planner result", key="pp_plan",
                               disabled="plan_result" not in st.session_state)
    with c2:
        can_export = can("export_evidence")
        gen = st.button("Generate Evidence Passport (PDF)", type="primary", width="stretch", key="pp_gen",
                        disabled=not can_export)
        if not can_export:
            deny_note("export_evidence")
    if gen:
        try:
            ACT.check(current_user(), audit_log(), "export_evidence", "PDF Evidence Passport")
        except PermissionDenied as e:
            st.error(f"Not permitted. {e}")
            gen = False
    if gen:
        if not ids:
            st.warning("Select at least one finding for the evidence sheets.")
        else:
            with st.spinner("Building PDF from the current analysis..."):
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                plan_t = st.session_state["plan_result"].table if inc_plan and "plan_result" in st.session_state else None
                pdf = build_pdf(res, latest, store.history(res.fingerprint), detail_ids=ids, generated_utc=ts,
                                plan_table=plan_t, extras=extras)
                st.session_state.pdf_bytes = pdf
                st.session_state.pdf_name = f"CorroSight_Evidence_Passport_{res.fingerprint[:8]}_{ts[:10]}.pdf"
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                (OUT_DIR / st.session_state.pdf_name).write_bytes(pdf)
                log_export(res, "PDF Evidence Passport", ids, st.session_state.pdf_name, extras["snapshot_id"])
                ACT.export(current_user(), audit_log(), "PDF Evidence Passport", st.session_state.pdf_name, res.fingerprint)
    d1, d2, d3 = st.columns(3)
    if not can_export:          # export bytes are never sent to the browser for roles without the capability
        for col, lab, k in ((d1, "Download PDF Evidence Passport", "dl_pdf_off"), (d2, "Download findings CSV", "dl_csv_off"),
                            (d3, "Download validation issues CSV", "dl_iss_off")):
            col.button(lab, disabled=True, width="stretch", key=k, help=rbac.explain("export_evidence"))
    else:
        _export_buttons(res, latest, extras, d1, d2, d3)
    st.markdown(f"##### Export preview ({len(table)} findings × {table.shape[1]} columns)")
    st.dataframe(table, width="stretch", hide_index=True, height=320)
    st.caption("Column prefixes OBSERVED / CALCULATED / UNCERTAINTY / PREDICTED / SCENARIO / SYSTEM / REVIEWER keep "
               "measurements, arithmetic, model outputs and human decisions distinguishable in the export.")


def _export_cb(res, kind, tracks, file, snapshot_id):
    log_export(res, kind, tracks, file, snapshot_id)
    ACT.export(current_user(), audit_log(), kind, file, res.fingerprint)


def _export_buttons(res, latest, extras, d1, d2, d3):
    csv_bytes = to_csv_bytes(res, latest, extras=extras)
    with d1:
        if st.session_state.get("pdf_bytes"):
            st.download_button("Download PDF Evidence Passport", st.session_state.pdf_bytes, st.session_state.pdf_name,
                               "application/pdf", width="stretch", key="dl_pdf")
            st.caption(f"{len(st.session_state.pdf_bytes) / 1024:.0f} KB · also saved to outputs/{st.session_state.pdf_name}")
        else:
            st.button("Download PDF Evidence Passport", disabled=True, width="stretch", key="dl_pdf_off",
                      help="Generate the PDF first.")
    d2.download_button("Download findings CSV", csv_bytes, f"CorroSight_findings_{res.fingerprint[:8]}.csv", "text/csv",
                       width="stretch", key="dl_csv",
                       on_click=_export_cb, args=(res, "Findings CSV", "all", f"CorroSight_findings_{res.fingerprint[:8]}.csv",
                                                  extras["snapshot_id"]))
    iss_name = f"CorroSight_validation_issues_{res.fingerprint[:8]}.csv"
    d3.download_button("Download validation issues CSV", res.issues.to_csv(index=False).encode("utf-8"),
                       iss_name, "text/csv", width="stretch", key="dl_iss",
                       on_click=_export_cb, args=(res, "Validation issues CSV", "all", iss_name, extras["snapshot_id"]))


def value_tab(res: AnalysisResult):
    st.markdown("<div class='cs-banner'>Hypothetical calculator. All inputs are assumptions; the review-time reduction in "
                "particular would have to be measured in a real pilot. No customers, revenue or validated savings are implied.</div>",
                unsafe_allow_html=True)
    c = st.columns(5)
    items = c[0].number_input("Items reviewed per year", 0, 1_000_000, int(len(res.findings)), 10, key="bv_items",
                              help="Default = number of findings in the current analysis.")
    hrs = c[1].number_input("Manual hours per item", 0.0, 100.0, 1.5, 0.25, key="bv_hrs")
    cost = c[2].number_input("Labour cost per hour", 0.0, 10_000.0, 60.0, 5.0, key="bv_cost")
    red = c[3].slider("Assumed time reduction %", 0, 100, 25, key="bv_red")
    fee = c[4].number_input("Illustrative annual fee", 0.0, 10_000_000.0, 10_000.0, 1000.0, key="bv_fee")
    r = calculate(ValueInputs(items, hrs, cost, red / 100, fee))
    k = st.columns(4)
    kpi(k[0], "Baseline review hours", f"{r.baseline_hours:,.0f}", "items × hours")
    kpi(k[1], "Hours saved (assumed)", f"{r.hours_saved:,.0f}", f"× {red}% assumption")
    kpi(k[2], "Estimated savings", f"{r.estimated_savings:,.0f}", "hypothetical")
    kpi(k[3], "Illustrative net value", f"{r.net_value:,.0f}", "savings − fee")
    st.markdown(f"`{items:,} items × {hrs:g} h × {cost:,.2f}/h × {red / 100:.2f} = {r.estimated_savings:,.0f}`  \n"
                f"`{r.estimated_savings:,.0f} − {fee:,.0f} fee = {r.net_value:,.0f}`")
    st.caption("Break-even time reduction: " + (f"{r.breakeven_reduction_fraction * 100:.1f}%" if r.breakeven_reduction_fraction
                                                 is not None else "not achievable at these inputs (fee exceeds total labour cost)"))


def planner_tab(res: AnalysisResult):
    st.markdown("<div class='cs-banner'>Optional, illustrative. Chooses review actions that maximise <b>modelled-benefit points</b> "
                "within a hypothetical budget (exact 0/1 knapsack). Points are demo assumptions per review category - they are "
                "not risk reduction or money saved. The output is a candidate plan for people to decide on.</div>",
                unsafe_allow_html=True)
    base = pd.DataFrame([dict(review_category=c, action=a, assumed_cost=cost, benefit_points=pts)
                         for c, (a, cost, pts) in DEFAULT_ACTION_ASSUMPTIONS.items()])
    edited = st.data_editor(base, width="stretch", hide_index=True, disabled=["review_category"], key="pl_assume",
                            column_config={"assumed_cost": st.column_config.NumberColumn(min_value=10, step=10),
                                           "benefit_points": st.column_config.NumberColumn(min_value=0, step=1)})
    c1, c2, c3 = st.columns([1, 1, 1])
    budget = c1.number_input("Hypothetical budget", 0.0, 10_000_000.0, 60_000.0, 1000.0, key="pl_budget")
    must = c2.checkbox("Must include every 'Review first' finding", key="pl_must")
    allowed = can("create_planning_scenario")
    run = c3.button("Optimise plan", type="primary", width="stretch", key="pl_run", disabled=not allowed)
    if not allowed:
        deny_note("create_planning_scenario")
    if run:
        try:
            ACT.check(current_user(), audit_log(), "create_planning_scenario", "budget planner")
        except PermissionDenied as e:
            st.error(f"Not permitted. {e}")
            return
        assume = {r.review_category: (r.action, float(r.assumed_cost), float(r.benefit_points)) for r in edited.itertuples()}
        st.session_state.plan_result = plan(res.findings, budget, assume, must)
        ACT.planning_scenario(current_user(), audit_log(), "budget planner", f"budget {budget:,.0f}; must-include {must}",
                              res.fingerprint)
        st.session_state.pop("pdf_bytes", None)
    p = st.session_state.get("plan_result")
    if p is None:
        st.info("Set a budget and press Optimise plan.")
        return
    (st.success if p.feasible else st.error)(p.message)
    k = st.columns(4)
    kpi(k[0], "Selected actions", int(p.table["selected"].sum()) if len(p.table) else 0, f"of {len(p.table)} candidates")
    kpi(k[1], "Assumed cost", f"{p.total_cost:,.0f}", f"budget {p.budget:,.0f}")
    kpi(k[2], "Benefit points", f"{p.total_benefit:,.0f}", "modelled, not risk")
    unresolved = p.table[~p.table["selected"] & (p.table["review_category"] == "Review first")] if len(p.table) else []
    kpi(k[3], "'Review first' not planned", len(unresolved), "remain unresolved")
    if len(p.table):
        by = p.table.groupby("review_category").agg(candidates=("track_id", "size"), selected=("selected", "sum"),
                                                     assumed_cost_selected=("assumed_cost", lambda c: float(c[p.table.loc[c.index, "selected"]].sum())))
        st.dataframe(by.reindex([c for c in CATEGORIES.values() if c in by.index]), width="stretch")
        st.dataframe(p.table, width="stretch", hide_index=True, height=360)


