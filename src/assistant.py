"""Evidence-grounded assistant (local, rule-based).

No language model and no external service is used: inspection data never leaves the machine. The assistant
recognises a small set of question types, retrieves the matching records from the current analysis and
explains the stored calculations, quoting finding IDs so the user can open them. When the loaded evidence
cannot answer a question, it says so instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .snapshots import compare

EXAMPLES = [
    "Why was T0177 prioritised?",
    "What evidence supports the match for T0163?",
    "Which measurement is missing for T0153?",
    "What assumptions influence the forecast for T0177?",
    "Why is T0163 marked ambiguous?",
    "Which records need additional verification?",
    "How do the forecasting methods compare?",
    "What changed between the last two snapshots?",
    "Summarise segment S18",
    "Which findings have contradictions?",
]


@dataclass
class Context:
    result: object
    reviews: dict = field(default_factory=dict)
    contradictions: pd.DataFrame | None = None
    anomalies: pd.DataFrame | None = None
    arena: dict | None = None
    snapshots: list = field(default_factory=list)


@dataclass
class Answer:
    text: str
    refs: list = field(default_factory=list)
    intent: str = "unknown"
    grounded: bool = True


def _fmt(v, nd=3):
    return "n/a" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{nd}f}"


def _track(q: str, F: pd.DataFrame) -> str | None:
    m = re.search(r"\bT\d{4}\b", q.upper())
    if m:
        return m.group(0)
    m = re.search(r"\b([A-Z]\d{2}-[A-Z0-9]+|Y\d+-\d{5})\b", q.upper())
    if m:
        hit = F[(F["obs_a"] == m.group(1)) | (F["obs_b"] == m.group(1))]
        if len(hit):
            return hit["track_id"].iloc[0]
    return None


def ask(question: str, ctx: Context) -> Answer:
    q = question.strip()
    ql = q.lower()
    res = ctx.result
    if res is None or not getattr(res, "ok", False):
        return Answer("No analysis is loaded, so there is no evidence to answer from. Load the demo dataset or upload data.",
                      intent="no_data", grounded=False)
    F = res.findings
    Fi = F.set_index("track_id")
    tid = _track(q, F)
    if re.search(r"\bT\d{4}\b", q.upper()) and tid not in Fi.index:
        return Answer(f"There is no finding {tid} in the loaded analysis, so I cannot answer about it.",
                      intent="unknown_finding", grounded=False)
    seg = re.search(r"\bS\d{2,3}\b", q.upper())

    if tid is not None:
        g = Fi.loc[tid]
        if any(w in ql for w in ("ambiguous", "match", "matched", "identity", "pairing")):
            alts = g["alternatives"] or "none within the gate"
            return Answer(
                f"**{tid}: {g['match_status_label']}.** {g['rationale']}\n\nCompeting candidates: {alts}. "
                "The normalised distance is a similarity measure, not a probability that the match is correct.",
                [tid], "match")
        if any(w in ql for w in ("missing", "measurement", "input", "readiness")):
            miss = g["inputs_missing"] or "none of the inputs CorroSight checks"
            return Answer(
                f"**{tid}** - engineering readiness: {g['readiness_label']}. Missing: {miss}. "
                f"Missing for the priority rules: {g['missing_inputs'] or 'nothing'}. "
                f"Needs verification: {g['requires_verification']}.", [tid], "missing")
        if any(w in ql for w in ("assumption", "forecast", "predict", "projection")):
            cfg = res.config
            return Answer(
                f"**{tid}** - {g['forecast_status_label']}. {g['forecast_reason']}\n\n"
                f"Assumptions: constant rate over {cfg.forecast_horizon_years:g} years after the later run; basis "
                f"'{g['forecast_basis']}'; {cfg.noise_k:g}-sigma measurement noise only (stated 1-sigma depth uncertainty "
                f"{_fmt(g['u_a'], 2)} / {_fmt(g['u_b'], 2)} mm); demo screening threshold {cfg.screening_threshold_pct_wt:g}% WT "
                f"(not a repair criterion). Observed rate {_fmt(g['rate_mm_per_yr'])} mm/yr; upper scenario rate "
                f"{_fmt(g['proj_rate_upper'])} mm/yr.", [tid], "forecast")
        if any(w in ql for w in ("why", "priorit", "rank", "category", "review first")):
            reasons = "\n".join(f"- {x}" for x in str(g["priority_explanation"]).split(" | "))
            return Answer(
                f"**{tid}** is in **{g['review_category']}** (condition: {g['condition_level']}, evidence: "
                f"{g['evidence_quality']}). Reasons:\n{reasons}\n\nProposed next step: {g['proposed_next_step']}. "
                "This is a review priority, not a risk score or failure probability.", [tid], "priority")
        # generic finding summary
        st = ctx.reviews.get(tid, {}).get("status", "Not reviewed")
        return Answer(
            f"**{tid}** ({g['match_status_label']}, segment {g['segment_id']}): earlier {g['obs_a']} "
            f"{_fmt(g['depth_a'], 2)} mm, later {g['obs_b']} {_fmt(g['depth_b'], 2)} mm, change {_fmt(g['delta_mm'], 2)} mm, "
            f"rate {_fmt(g['rate_mm_per_yr'])} mm/yr. Category {g['review_category']}. Review status: {st}.", [tid], "summary")

    if seg:
        sid = seg.group(0)
        S = F[F["segment_id"] == sid]
        if S.empty:
            return Answer(f"Segment {sid} has no findings in the loaded analysis.", intent="segment", grounded=False)
        top = S.sort_values("priority_order").head(5)
        cats = S["review_category"].value_counts().to_dict()
        return Answer(f"**Segment {sid}**: {len(S)} findings; categories {cats}; max latest depth "
                      f"{_fmt(S['latest_pct_wt'].max(), 1)}% WT; median observed rate (likely matches) "
                      f"{_fmt(S.loc[S['match_status'] == 'LIKELY_MATCH', 'rate_mm_per_yr'].median())} mm/yr. "
                      f"Highest priority: {', '.join(top['track_id'])}.", top["track_id"].tolist(), "segment")
    if any(w in ql for w in ("verif", "need additional", "need more", "check")):
        V = F[F["review_rank"].isin([2, 3])]
        V = V.sort_values("priority_order").head(12)
        lines = "\n".join(f"- {r.track_id}: {r.review_category} - {str(r.evidence_reasons).split(' | ')[0]}" for r in V.itertuples())
        n = int(F["review_rank"].isin([2, 3]).sum())
        return Answer(f"{n} findings are in 'Verify match / data' or 'Additional data needed'. Highest in order:\n{lines}",
                      V["track_id"].tolist(), "verification")
    if any(w in ql for w in ("method", "model", "compare", "shrinkage", "baseline")) and "snapshot" not in ql:
        a = ctx.arena
        if not a or not a.get("ok"):
            return Answer("Model comparison needs the synthetic ground truth (demo dataset). It is not available for "
                          "the loaded data, so I cannot compare accuracy.", intent="models", grounded=False)
        S = a["summary"].sort_values("rmse")
        lines = "\n".join(f"- {r.method_name}: MAE {r.mae:.4f}, RMSE {r.rmse:.4f} mm/yr, bias {r.bias:+.4f}, "
                          f"{a['k']:g}-sigma coverage {r.coverage:.2f}" for r in S.itertuples())
        return Answer(f"On held-out synthetic defects ({a['seeds']} group-wise 50/50 splits, ~{int(S['n_test'].iloc[0])} "
                      f"test defects each):\n{lines}\n\nSynthetic results only; they do not establish real-world accuracy.",
                      intent="models")
    if "snapshot" in ql or "changed" in ql:
        if len(ctx.snapshots) < 2:
            return Answer(f"{len(ctx.snapshots)} snapshot(s) saved for this dataset; two are needed to compare.",
                          intent="snapshots", grounded=False)
        a, b = ctx.snapshots[-2], ctx.snapshots[-1]
        c = compare(a, b)
        cfg = "; ".join(f"{r.setting}: {r.before} -> {r.after}" for r in c["config"].itertuples()) or "no setting changes"
        meta = "; ".join(f"{r.item}" for r in c["metadata"].itertuples()) or "same data, software and algorithms"
        return Answer(f"From **{a['snapshot_id']}** to **{b['snapshot_id']}**: {len(c['findings'])} finding(s) changed; "
                      f"settings: {cfg}; metadata: {meta}; review status changes: {len(c['reviews'])}.",
                      c["findings"]["track_id"].head(10).tolist() if len(c["findings"]) else [], "snapshots")
    if "contradict" in ql or "conflict" in ql:
        C = ctx.contradictions
        if C is None or C.empty:
            return Answer("No contradictions were found by rules K1-K8 in the loaded analysis.", intent="contradictions")
        lines = "\n".join(f"- {r.track_id}: {r.title}" for r in C.head(10).itertuples())
        return Answer(f"{len(C)} contradiction(s) across {C['track_id'].nunique()} findings. First ones:\n{lines}",
                      C["track_id"].head(10).tolist(), "contradictions")
    if any(w in ql for w in ("anomal", "suspicious", "outlier")):
        A = ctx.anomalies
        if A is None or A.empty:
            return Answer("No measurement anomalies were flagged.", intent="anomalies")
        lines = "\n".join(f"- {r.flag_id} {r.observation_id}: {r.check} ({r.severity})" for r in A.head(10).itertuples())
        return Answer(f"{len(A)} flags ({(A['severity'] == 'High').sum()} High). First ones:\n{lines}",
                      A["track_id"].dropna().head(10).tolist(), "anomalies")
    if any(w in ql for w in ("how many", "summary", "summarise", "summarize", "overview")):
        s = res.summary()
        return Answer(f"{s['n_findings']} findings from {s['run_a']} ({s['date_a']}) and {s['run_b']} ({s['date_b']}). "
                      f"Matches: {s['match_counts']}. Review categories: {s['review_counts']}. "
                      f"Validation: {s['issue_counts']}.", intent="summary")
    return Answer("I could not find evidence in the loaded analysis that answers this. I can explain a finding's priority, "
                  "match evidence, missing inputs or forecast assumptions (include its ID, e.g. T0177), list records "
                  "needing verification, contradictions or anomalies, summarise a segment (e.g. S18), compare forecasting "
                  "methods, or compare snapshots.", intent="unknown", grounded=False)
