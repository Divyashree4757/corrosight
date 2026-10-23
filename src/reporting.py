"""Evidence Passport: CSV and PDF exports built from the SAME AnalysisResult the dashboard displays.

`findings_frame()` is the single source for the findings table on screen, the CSV export and the PDF
tables, which is what keeps the three consistent (verified in tests/test_reporting.py).
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from . import APP_NAME
from .assessment import SCOPE_TABLE
from .pipeline import AnalysisResult
from .schema import DEMO_ASSUMPTION_NOTE, LIMITATIONS

# (column in findings, export header)
EXPORT_COLUMNS = [
    ("priority_order", "priority_order"),
    ("track_id", "finding_id"),
    ("review_category", "review_category"),
    ("condition_level", "condition_indicators"),
    ("evidence_quality", "evidence_quality"),
    ("match_status_label", "match_status"),
    ("segment_id", "segment_id"),
    ("joint_id", "joint_id"),
    ("obs_a", "earlier_observation_id"),
    ("obs_b", "later_observation_id"),
    ("pos_a", "earlier_axial_position_m"),
    ("pos_b", "later_axial_position_m"),
    ("d_pos_aligned_m", "aligned_position_difference_m"),
    ("d_clock_h", "clock_difference_h"),
    ("distance", "match_distance"),
    ("agreement", "match_agreement_index"),
    ("depth_a", "OBSERVED_earlier_depth_mm"),
    ("depth_b", "OBSERVED_later_depth_mm"),
    ("u_a", "earlier_depth_uncertainty_mm_1sigma"),
    ("u_b", "later_depth_uncertainty_mm_1sigma"),
    ("wt_mm", "nominal_wt_mm"),
    ("latest_pct_wt", "CALCULATED_latest_depth_pct_wt"),
    ("dt_years", "CALCULATED_elapsed_years"),
    ("delta_mm", "CALCULATED_observed_change_mm"),
    ("rate_mm_per_yr", "CALCULATED_annualised_change_mm_per_yr"),
    ("sigma_rate_mm_per_yr", "UNCERTAINTY_rate_sigma_mm_per_yr"),
    ("rate_low", "UNCERTAINTY_rate_low_k_sigma"),
    ("rate_high", "UNCERTAINTY_rate_high_k_sigma"),
    ("change_class_label", "change_vs_noise"),
    ("shrunk_rate_mm_per_yr", "PREDICTED_model_b_shrinkage_rate_mm_per_yr"),
    ("forecast_status_label", "forecast_status"),
    ("forecast_basis", "forecast_basis"),
    ("proj_depth_central_mm", "PREDICTED_central_depth_at_horizon_mm"),
    ("proj_depth_upper_mm", "PREDICTED_upper_scenario_depth_at_horizon_mm"),
    ("proj_pct_upper", "PREDICTED_upper_scenario_pct_wt_at_horizon"),
    ("yrs_to_threshold_upper", "SCENARIO_years_to_demo_threshold_upper"),
    ("forecast_reason", "forecast_reason_or_limitation"),
    ("priority_explanation", "priority_explanation"),
    ("missing_inputs", "missing_inputs"),
    ("readiness_label", "engineering_readiness"),
    ("inputs_missing", "readiness_inputs_missing"),
    ("requires_verification", "readiness_requires_verification"),
    ("rationale", "match_rationale"),
    ("flags_a", "earlier_record_quality_flags"),
    ("flags_b", "later_record_quality_flags"),
    ("proposed_next_step", "SYSTEM_proposed_next_step"),
]
REVIEW_COLUMNS = ["review_status", "REVIEWER_selected_next_step", "reviewer", "review_notes", "review_timestamp_utc"]


def _join_by_track(df, col, tracks) -> list[str]:
    if df is None or len(df) == 0:
        return [""] * len(tracks)
    g = df.dropna(subset=["track_id"]).groupby("track_id")[col].apply(lambda s: "; ".join(dict.fromkeys(map(str, s))))
    return [g.get(t, "") for t in tracks]


def findings_frame(result: AnalysisResult, reviews: dict[str, dict] | None = None, extras: dict | None = None) -> pd.DataFrame:
    """Canonical findings table used by the dashboard, CSV and PDF.

    `extras` (optional) adds cross-feature evidence computed by the same session: anomaly flags, contradictions,
    evidence gaps, reviewer identity resolutions and the analysis snapshot id.
    """
    F = result.findings
    out = pd.DataFrame({hdr: F[col].to_numpy() for col, hdr in EXPORT_COLUMNS})
    reviews = reviews or {}
    out["review_status"] = [reviews.get(t, {}).get("status", "Not reviewed") for t in out["finding_id"]]
    out["REVIEWER_selected_next_step"] = [reviews.get(t, {}).get("reviewer_selected_next_step", "") for t in out["finding_id"]]
    out["reviewer"] = [reviews.get(t, {}).get("reviewer", "") for t in out["finding_id"]]
    out["review_notes"] = [reviews.get(t, {}).get("notes", "") for t in out["finding_id"]]
    out["review_timestamp_utc"] = [reviews.get(t, {}).get("timestamp_utc", "") for t in out["finding_id"]]
    if extras:
        ids = out["finding_id"].tolist()
        out["ANALYSIS_anomaly_flags"] = _join_by_track(extras.get("anomalies"), "check", ids)
        out["ANALYSIS_contradictions"] = _join_by_track(extras.get("contradictions"), "title", ids)
        out["ANALYSIS_evidence_gaps"] = _join_by_track(extras.get("gaps"), "gap_type", ids)
        res = extras.get("resolutions") or {}
        out["REVIEWER_identity_resolution"] = [f"{res[t]['resolution']} {res[t].get('alternative', '')}".strip()
                                               if t in res else "" for t in ids]
        out["analysis_snapshot_id"] = extras.get("snapshot_id") or ""
    # round numeric columns once, here, so screen / CSV / PDF show identical values
    for c in out.columns:
        if pd.api.types.is_float_dtype(out[c]):
            out[c] = out[c].round(4)
    out = out.replace([np.inf], np.nan).infer_objects()
    return out


def metadata(result: AnalysisResult, generated_utc: str) -> dict:
    s = result.summary()
    return {
        "report": "CorroSight Evidence Passport",
        "generated_utc": generated_utc,
        "software": f"{APP_NAME} v{result.software_version}",
        "dataset": result.source.name,
        "synthetic_data": "YES - fictional demonstration data" if result.source.synthetic else "No (user-supplied)",
        "source_files": ", ".join(result.source.files),
        "dataset_sha256": result.fingerprint,
        "analysis_created_utc": result.created_utc,
        "runs_compared": f"{s['run_a']} ({s['date_a']}) -> {s['run_b']} ({s['date_b']}), {s['years_between']:.2f} yr",
        "forecast_method": result.config.forecast_method,
    }


def to_csv_bytes(result: AnalysisResult, reviews: dict | None = None, generated_utc: str | None = None,
                 extras: dict | None = None) -> bytes:
    gen = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    df = findings_frame(result, reviews, extras)
    meta = metadata(result, gen)
    df.insert(0, "report_generated_utc", gen)
    df.insert(1, "dataset_sha256", meta["dataset_sha256"])
    df.insert(2, "software_version", result.software_version)
    df.insert(3, "synthetic_data", result.source.synthetic)
    df["limitations"] = "Prototype. Review priority is not risk or failure probability. Qualified engineering review required."
    return df.to_csv(index=False).encode("utf-8")


# ---------------------------------------------------------------- PDF ----------------------------------------
NAVY = colors.HexColor("#0F1F2C")
TEAL = colors.HexColor("#1F9E92")
LIGHT = colors.HexColor("#EEF4F6")
AMBER = colors.HexColor("#B7791F")
RED = colors.HexColor("#9B2C2C")

CAT_COLOURS = {"Review first": RED, "Verify match / data": AMBER, "Additional data needed": colors.HexColor("#6B46C1"),
               "Monitor": TEAL, "Routine review": colors.HexColor("#4A5568")}


def _styles():
    ss = getSampleStyleSheet()
    st = {
        "title": ParagraphStyle("t", parent=ss["Title"], textColor=NAVY, fontSize=20, leading=24, alignment=TA_LEFT),
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], textColor=NAVY, fontSize=14, spaceBefore=8, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], textColor=TEAL, fontSize=11, spaceBefore=6, spaceAfter=3),
        "body": ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.5, leading=11),
        "small": ParagraphStyle("s", parent=ss["BodyText"], fontSize=7, leading=8.6),
        "cell": ParagraphStyle("c", parent=ss["BodyText"], fontSize=7, leading=8.4),
        "banner": ParagraphStyle("bn", parent=ss["BodyText"], fontSize=8.5, leading=11, textColor=colors.white),
    }
    return st


def _p(text, style):
    return Paragraph(escape("" if text is None else str(text)).replace("\n", "<br/>"), style)


def _fmt(v, nd=2):
    if v is None or (isinstance(v, float) and (np.isnan(v))):
        return "-"
    if isinstance(v, (float, np.floating)):
        if np.isinf(v):
            return "not reached"
        return f"{v:.{nd}f}"
    return str(v)


def _table(rows, widths, st, header=True, zebra=True):
    data = [[c if isinstance(c, Paragraph) else _p(c, st["cell"]) for c in r] for r in rows]
    if header:
        data[0] = [Paragraph(f"<font color='white'><b>{escape(str(c))}</b></font>", st["cell"]) for c in rows[0]]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8C4CC")),
             ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
             ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), NAVY)]
    if zebra:
        for i in range(1 if header else 0, len(rows)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    t.setStyle(TableStyle(style))
    return t


def build_pdf(result: AnalysisResult, reviews: dict | None = None, review_history: list[dict] | None = None,
              detail_ids: list[str] | None = None, max_details: int = 10, generated_utc: str | None = None,
              plan_table: pd.DataFrame | None = None, extras: dict | None = None) -> bytes:
    gen = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    st = _styles()
    s = result.summary()
    meta = metadata(result, gen)
    ex = extras or {}
    if ex.get("snapshot_id"):
        meta["analysis_snapshot_id"] = ex["snapshot_id"]
    F = findings_frame(result, reviews, extras)
    full = result.findings.set_index("track_id")
    cfg = result.config
    buf = io.BytesIO()
    page = landscape(A4)
    W = page[0] - 24 * mm

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, page[1] - 10 * mm, page[0], 10 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(12 * mm, page[1] - 6.5 * mm, "CorroSight Evidence Passport")
        canvas.setFont("Helvetica", 7.5)
        tag = "SYNTHETIC DEMO DATA - " if result.source.synthetic else ""
        canvas.drawRightString(page[0] - 12 * mm, page[1] - 6.5 * mm,
                               f"{tag}Prototype - not a certified integrity assessment")
        canvas.setFillColor(colors.HexColor("#4A5568"))
        canvas.drawString(12 * mm, 7 * mm, f"Generated {gen} | dataset SHA-256 {result.fingerprint[:16]}... | v{result.software_version}")
        canvas.drawRightString(page[0] - 12 * mm, 7 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=15 * mm, bottomMargin=13 * mm, title="CorroSight Evidence Passport",
                            author=APP_NAME, subject=result.source.name)
    E = []
    E.append(Paragraph("CorroSight Evidence Passport", st["title"]))
    E.append(_p(f"{APP_NAME} - pipeline inspection comparison, explainable review priorities and evidence trail.", st["body"]))
    E.append(Spacer(1, 4))
    banner_txt = ("This report was generated from FICTIONAL SYNTHETIC data for demonstration. "
                  if result.source.synthetic else "") + \
        ("Review priorities are recommendations for human review. They are not risk classifications, failure "
         "probabilities or repair decisions. No remaining-strength assessment is performed. Qualified engineering "
         "review is required before any action.")
    bt = Table([[_p(banner_txt, st["banner"])]], colWidths=[W])
    bt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEAL), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    E.append(bt)
    E.append(Spacer(1, 6))

    # --- 1. Inspection evidence ---
    E.append(Paragraph("1. Inspection evidence", st["h1"]))
    rows = [["Item", "Value"]] + [[k.replace("_", " "), v] for k, v in meta.items()]
    rows += [["pipeline id(s)", ", ".join(s["pipeline_ids"]) or "-"],
             ["records (earlier / later run)", f"{s['n_records_a']} / {s['n_records_b']}"],
             ["segments covered", s["n_segments"]],
             ["findings (tracks)", s["n_findings"]]]
    E.append(_table(rows, [60 * mm, W - 60 * mm], st))

    # --- 2. Validation ---
    E.append(Paragraph("2. Data validation findings", st["h1"]))
    ic = s["issue_counts"]
    E.append(_p(f"Errors: {ic['Error']}   Warnings: {ic['Warning']}   Info: {ic['Info']}. "
                "Source records are never deleted or modified; problem records are flagged and excluded only "
                "from the calculation they would corrupt.", st["body"]))
    iss = result.issues
    if len(iss):
        rows = [["ID", "Severity", "Code", "Run", "Observation", "Message", "Effect on analysis", "Suggested action"]]
        for r in iss.itertuples():
            rows.append([r.issue_id, r.severity, r.code, _fmt(r.run_id), _fmt(r.observation_id), r.message, r.effect, r.action])
        E.append(_table(rows, [11 * mm, 15 * mm, 33 * mm, 15 * mm, 20 * mm, 70 * mm, 55 * mm, W - 219 * mm], st))
    for line in result.validation.log:
        E.append(_p("Log: " + line, st["small"]))

    # --- 3. Matching ---
    E.append(PageBreak())
    E.append(Paragraph("3. Corrosion Memory Graph - matching decisions", st["h1"]))
    mc = s["match_counts"]
    rows = [["Match status", "Count", "Meaning"],
            ["Likely match", mc["LIKELY_MATCH"], "One-to-one pairing with no competing candidate within the ambiguity margin."],
            ["Ambiguous match", mc["AMBIGUOUS"], "Provisional pairing; another candidate fits almost as well. Not used for forecasts."],
            ["Not found in later run", mc["UNMATCHED_EARLIER"], "Earlier record with no later partner."],
            ["New in later run", mc["NEW_LATER"], "Later record with no earlier partner (new, previously undetected, or false call)."],
            ["Excluded from matching", mc["EXCLUDED"], "Duplicate, missing identifier or invalid location; record retained."]]
    E.append(_table(rows, [45 * mm, 18 * mm, W - 63 * mm], st))
    off = result.match.offsets
    E.append(_p(
        f"Method: per-segment odometer alignment (offset range {off['offset_m'].min():+.2f} to {off['offset_m'].max():+.2f} m), "
        f"spatial gates |dx| <= {cfg.pos_gate_m} m and |dclock| <= {cfg.clock_gate_h} h, normalised distance cost "
        f"(scales {cfg.pos_scale_m} m, {cfg.clock_scale_h} h, {cfg.length_scale_mm} mm), one-to-one Hungarian assignment, "
        f"ambiguity margin {cfg.ambiguity_margin}. Depth is not used for matching. The agreement index exp(-d^2/2) is a "
        "similarity measure, not a probability.", st["body"]))
    if result.evaluation and result.source.synthetic:
        ev = result.evaluation["matching"]
        E.append(Paragraph("Evaluation against synthetic ground truth (synthetic only - not real-world accuracy)", st["h2"]))
        rows = [["Metric", "Value"],
                ["True cross-run pairs in data", ev["true_pairs"]],
                ["Likely-match precision", f"{ev['likely']['precision']:.3f} ({ev['likely']['correct']}/{ev['likely']['predicted_pairs']})"],
                ["Ambiguous-pair precision", f"{ev['ambiguous']['precision']:.3f} ({ev['ambiguous']['correct']}/{ev['ambiguous']['predicted_pairs']})"],
                ["Recall (likely + ambiguous)", f"{ev['recall_all_assigned']:.3f}"],
                ["Recall (likely only)", f"{ev['recall_likely_only']:.3f}"],
                ["False matches / missed true pairs", f"{ev['all_assigned']['false_matches']} / {ev['missed_true_pairs']}"]]
        E.append(_table(rows, [80 * mm, 60 * mm], st))

    # --- 4. Growth and forecast ---
    E.append(Paragraph("4. Growth estimation, forecast and uncertainty", st["h1"]))
    G = result.growth
    cc = G["change_class_label"].value_counts().to_dict()
    fc = G["forecast_status_label"].value_counts().to_dict()
    rows = [["Change vs measurement noise", "Count"]] + [[k, v] for k, v in cc.items()]
    rows2 = [["Forecast status", "Count"]] + [[k, v] for k, v in fc.items()]
    E.append(Table([[_table(rows, [80 * mm, 20 * mm], st), _table(rows2, [100 * mm, 20 * mm], st)]],
                   colWidths=[110 * mm, 130 * mm], style=[("VALIGN", (0, 0), (-1, -1), "TOP")]))
    sh = result.shrinkage
    E.append(_p(
        "Observed change = later depth - earlier depth (mm); annualised change = change / elapsed years. Negative changes are "
        f"kept as observed. Measurement-noise sigma = sqrt(u1^2 + u2^2) using stated 1-sigma depth uncertainties; the "
        f"{cfg.noise_k:g}-sigma interval covers measurement noise only (not matching, sizing bias or model form). "
        f"Projections assume a constant rate over a {cfg.forecast_horizon_years:g}-year horizon and are illustrative. "
        f"Forecast method selected: {cfg.forecast_method}. "
        + (f"Model B shrinkage fit: population mean {sh.mu:.4f} mm/yr, between-defect variance {sh.tau2:.5f} (n={sh.n})."
           if sh and sh.fitted else "Model B shrinkage: not fitted (insufficient data)."), st["body"]))
    if result.evaluation and result.source.synthetic and result.evaluation["growth"].get("n", 0):
        eg = result.evaluation["growth"]
        rows = [["Rate estimator (synthetic ground truth, n=%d)" % eg["n"], "MAE mm/yr", "RMSE mm/yr", "Bias mm/yr",
                 f"{eg['k']:g}-sigma interval coverage"],
                ["Baseline: per-defect observed rate", f"{eg['baseline']['mae']:.4f}", f"{eg['baseline']['rmse']:.4f}",
                 f"{eg['baseline']['bias']:+.4f}", f"{eg['baseline_interval_coverage']:.3f}"],
                ["Model B: empirical-Bayes shrinkage", f"{eg['shrinkage']['mae']:.4f}", f"{eg['shrinkage']['rmse']:.4f}",
                 f"{eg['shrinkage']['bias']:+.4f}", f"{eg['shrinkage_interval_coverage']:.3f}"]]
        E.append(Spacer(1, 3))
        E.append(_table(rows, [80 * mm, 30 * mm, 30 * mm, 30 * mm, 45 * mm], st))
        E.append(_p("Synthetic measurement noise was generated with exactly the stated uncertainty, so interval coverage here "
                    "is optimistic by construction. These metrics do not establish real-world accuracy.", st["small"]))

    # --- 5. Priorities ---
    E.append(PageBreak())
    E.append(Paragraph("5. Why-Inspect-First review priorities", st["h1"]))
    rc = s["review_counts"]
    E.append(_p("Category counts: " + "; ".join(f"{k}: {rc.get(k, 0)}" for k in CAT_COLOURS) + ". "
                "Category = the higher of the condition-based and evidence-based categories, so missing or uncertain "
                "evidence can only raise a finding. " + DEMO_ASSUMPTION_NOTE, st["body"]))
    E.append(_p(f"Demo thresholds: depth review {cfg.depth_review_pct_wt:g}% WT; rate review {cfg.rate_review_mm_per_yr:g} mm/yr "
                f"(beyond {cfg.noise_k:g}-sigma noise); screening threshold {cfg.screening_threshold_pct_wt:g}% WT within "
                f"{cfg.forecast_horizon_years:g} yr (upper scenario).", st["body"]))
    top = F[F["review_category"] != "Routine review"]
    rows = [["#", "Finding", "Category", "Condition", "Evidence", "Match", "Obs (earlier -> later)", "Latest %WT",
             "Rate mm/yr", "System proposed next step", "Review status"]]
    for r in top.itertuples():
        rows.append([r.priority_order, r.finding_id, r.review_category, r.condition_indicators, r.evidence_quality,
                     r.match_status, f"{_fmt(r.earlier_observation_id)} -> {_fmt(r.later_observation_id)}",
                     _fmt(r.CALCULATED_latest_depth_pct_wt, 1), _fmt(r.CALCULATED_annualised_change_mm_per_yr, 3),
                     r.SYSTEM_proposed_next_step, r.review_status])
    E.append(_table(rows, [9 * mm, 15 * mm, 27 * mm, 20 * mm, 17 * mm, 25 * mm, 38 * mm, 15 * mm, 16 * mm, 50 * mm, W - 232 * mm], st))
    E.append(_p(f"{int((F['review_category'] == 'Routine review').sum())} findings in 'Routine review' are listed in the CSV export.",
                st["small"]))

    # --- 6. Finding detail sheets ---
    ids = detail_ids or F["finding_id"].head(max_details).tolist()
    E.append(PageBreak())
    E.append(Paragraph(f"6. Finding evidence sheets ({len(ids)})", st["h1"]))
    for tid in ids:
        if tid not in full.index:
            continue
        g = full.loc[tid]
        fr = F[F["finding_id"] == tid].iloc[0]
        block = [Paragraph(f"{tid} - {escape(g['review_category'])} - {escape(g['match_status_label'])}", st["h2"])]
        ev_rows = [["Evidence", f"Earlier ({result.match.run_a}, {s['date_a']})", f"Later ({result.match.run_b}, {s['date_b']})"],
                   ["Observation ID (source record)", _fmt(g["obs_a"]), _fmt(g["obs_b"])],
                   ["OBSERVED axial position m", _fmt(g["pos_a"], 3), _fmt(g["pos_b"], 3)],
                   ["OBSERVED clock h", _fmt(g["clock_a"]), _fmt(g["clock_b"])],
                   ["OBSERVED depth mm (1-sigma)", f"{_fmt(g['depth_a'])} ({_fmt(g['u_a'])})", f"{_fmt(g['depth_b'])} ({_fmt(g['u_b'])})"],
                   ["OBSERVED length / width mm", f"{_fmt(g['length_a'], 0)} / {_fmt(g['width_a'], 0)}", f"{_fmt(g['length_b'], 0)} / {_fmt(g['width_b'], 0)}"],
                   ["Nominal WT mm (design)", _fmt(g["wt_a"]), _fmt(g["wt_b"])],
                   ["Record quality flags", _fmt(g["flags_a"]) or "-", _fmt(g["flags_b"]) or "-"]]
        calc_rows = [["Result", "Value"],
                     ["CALCULATED observed change", f"{_fmt(g['delta_mm'])} mm over {_fmt(g['dt_years'])} yr"],
                     ["CALCULATED annualised change", f"{_fmt(g['rate_mm_per_yr'], 3)} mm/yr"],
                     ["UNCERTAINTY (measurement only)", f"sigma {_fmt(g['sigma_rate_mm_per_yr'], 3)} mm/yr; "
                                                        f"{cfg.noise_k:g}-sigma range {_fmt(g['rate_low'], 3)} to {_fmt(g['rate_high'], 3)}"],
                     ["Change vs noise", g["change_class_label"]],
                     ["Latest depth % WT", _fmt(g["latest_pct_wt"], 1)],
                     ["PREDICTED (illustrative)", f"{g['forecast_status_label']}: central {_fmt(g['proj_depth_central_mm'])} mm, "
                                                  f"upper {_fmt(g['proj_depth_upper_mm'])} mm at +{cfg.forecast_horizon_years:g} yr"],
                     ["Years to demo threshold (upper)", _fmt(g["yrs_to_threshold_upper"], 1)],
                     ["Forecast limitation", g["forecast_reason"]]]
        block.append(Table([[_table(ev_rows, [45 * mm, 38 * mm, 38 * mm], st), _table(calc_rows, [42 * mm, W - 175 * mm], st)]],
                           colWidths=[124 * mm, W - 124 * mm], style=[("VALIGN", (0, 0), (-1, -1), "TOP"),
                                                                      ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        why_rows = [["Basis", "Detail"],
                    ["Match rationale", g["rationale"]],
                    ["Condition indicators", g["condition_reasons"]],
                    ["Evidence quality", f"{g['evidence_quality']}: {g['evidence_reasons']}"],
                    ["Engineering readiness", f"{g['readiness_label']}. Missing: {g['inputs_missing'] or 'none'}. "
                                              f"Verify: {g['requires_verification']}"],
                    ["System proposed next step", g["proposed_next_step"]],
                    ["Human review", f"{fr['review_status']}"
                                     + (f" | reviewer-selected step: {fr['REVIEWER_selected_next_step']} | by {fr['reviewer']} at "
                                        f"{fr['review_timestamp_utc']} | notes: {fr['review_notes'] or '-'}" if fr['review_timestamp_utc'] else "")]]
        if extras:
            why_rows += [["Anomaly flags", fr.get("ANALYSIS_anomaly_flags") or "none"],
                         ["Contradictions", fr.get("ANALYSIS_contradictions") or "none"],
                         ["Evidence gaps", fr.get("ANALYSIS_evidence_gaps") or "none"],
                         ["Identity resolution (reviewer)", fr.get("REVIEWER_identity_resolution") or "none recorded"]]
        block.append(Spacer(1, 2))
        block.append(_table(why_rows, [42 * mm, W - 42 * mm], st))
        block.append(Spacer(1, 6))
        E.append(KeepTogether(block))

    # --- 7. Planning (optional) ---
    if plan_table is not None and len(plan_table):
        E.append(PageBreak())
        E.append(Paragraph("7. Candidate review plan (budget planner - illustrative)", st["h1"]))
        E.append(_p("Benefit points and costs are demo assumptions. The plan is a candidate for human decision; nothing is approved.",
                    st["body"]))
        sel = plan_table[plan_table["selected"]]
        rows = [["Finding", "Category", "Action", "Assumed cost", "Benefit points", "Reason"]]
        for r in sel.itertuples():
            rows.append([r.track_id, r.review_category, r.action, f"{r.assumed_cost:,.0f}", f"{r.benefit_points:g}", r.decision_reason])
        E.append(_table(rows, [20 * mm, 35 * mm, 50 * mm, 25 * mm, 25 * mm, W - 155 * mm], st))

    # --- 7b. Cross-checks, model evaluation, resolutions and corrections (when provided) ---
    if extras:
        E.append(PageBreak())
        E.append(Paragraph("7b. Contradictions, anomalies, evidence gaps and reviewer proposals", st["h1"]))
        A, K, Gp = ex.get("anomalies"), ex.get("contradictions"), ex.get("gaps")
        E.append(_p(f"Measurement anomaly flags: {0 if A is None else len(A)}; contradictions: {0 if K is None else len(K)}; "
                    f"evidence gaps: {0 if Gp is None else len(Gp)}. Flags mark measurements to check; they are not corrosion "
                    "events and no source value was changed.", st["body"]))
        if K is not None and len(K):
            rows = [["Finding", "Rule", "Evidence A", "Evidence B", "Conflict", "Would resolve"]]
            for r in K.head(40).itertuples():
                rows.append([r.track_id, f"{r.rule} {r.title}", r.evidence_a, r.evidence_b, r.conflict, r.resolve_with])
            E.append(_table(rows, [16 * mm, 40 * mm, 55 * mm, 55 * mm, 55 * mm, W - 221 * mm], st))
        res = ex.get("resolutions") or {}
        cor = ex.get("corrections") or []
        if res or cor:
            E.append(Paragraph("Reviewer proposals (recorded separately; the analysis is unchanged)", st["h2"]))
            rows = [["Finding / record", "Type", "Proposal", "Rationale", "Reviewer", "Time (UTC)"]]
            for t, e in res.items():
                rows.append([t, "Identity resolution", f"{e['resolution']} {e.get('alternative', '')}", e["rationale"], e["reviewer"],
                             e["timestamp_utc"]])
            for e in cor:
                rows.append([f"{e['run_id']}/{e['observation_id']}", "Measurement correction (not applied)",
                             f"{e['field']}: {e['original_value']} -> {e['proposed_value']}", e["rationale"], e["reviewer"],
                             e["timestamp_utc"]])
            E.append(_table(rows, [35 * mm, 45 * mm, 55 * mm, 70 * mm, 25 * mm, W - 230 * mm], st))
        ar = ex.get("arena")
        if ar and ar.get("ok") and result.source.synthetic:
            E.append(Paragraph("Model Challenge Arena (held-out synthetic defects; not real-world accuracy)", st["h2"]))
            rows = [["Method", "MAE", "RMSE", "Bias", f"{ar['k']:g}-sigma coverage", "Lowest RMSE in splits"]]
            for r in ar["summary"].sort_values("rmse").itertuples():
                rows.append([r.method_name, f"{r.mae:.4f}", f"{r.rmse:.4f}", f"{r.bias:+.4f}", f"{r.coverage:.3f}",
                             f"{r.lowest_rmse_in_splits}/{ar['seeds']}"])
            E.append(_table(rows, [70 * mm, 25 * mm, 25 * mm, 25 * mm, 35 * mm, 40 * mm], st))

    # --- 8. Review log ---
    E.append(PageBreak())
    E.append(Paragraph("8. Human review log", st["h1"]))
    hist = review_history or []
    if hist:
        rows = [["Timestamp (UTC)", "Finding", "Status", "System proposed", "Reviewer selected", "Reviewer", "Reason / notes"]]
        for h in hist:
            rows.append([h["timestamp_utc"], h["track_id"], h["status"] + (" (reopened)" if h.get("action") == "reopened" else ""),
                         h["system_proposed_next_step"], h["reviewer_selected_next_step"], h["reviewer"],
                         " | ".join(x for x in (h.get("reason", ""), h.get("notes", "")) if x)])
        E.append(_table(rows, [32 * mm, 16 * mm, 38 * mm, 50 * mm, 50 * mm, 25 * mm, W - 211 * mm], st))
    else:
        E.append(_p("No human review decisions have been recorded for this dataset.", st["body"]))
    E.append(_p("CorroSight records review status only. It does not approve repairs, authorise work orders or change "
                "operating conditions. A closed review is not a verified repair. This Evidence Passport records analysis "
                "and review evidence; it does not certify pipeline safety or regulatory compliance.", st["body"]))

    # --- 9. Scope, configuration and limitations ---
    E.append(Paragraph("9. Scope, configuration and limitations", st["h1"]))
    rows = [["Question", "Status in CorroSight", "Explanation"]] + [list(r) for r in SCOPE_TABLE]
    E.append(_table(rows, [55 * mm, 45 * mm, W - 100 * mm], st))
    E.append(Spacer(1, 4))
    rows = [["Setting (demo assumption unless stated)", "Value"]] + [[k, str(v)] for k, v in cfg.to_dict().items()]
    E.append(_table(rows, [80 * mm, 50 * mm], st))
    E.append(Paragraph("Limitations", st["h2"]))
    for lim in LIMITATIONS:
        E.append(_p("- " + lim, st["body"]))
    E.append(Spacer(1, 10))
    E.append(_table([["Qualified reviewer name", "Role", "Signature", "Date"], ["", "", "", ""]],
                    [70 * mm, 60 * mm, 70 * mm, W - 200 * mm], st, zebra=False))

    doc.build(E, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
