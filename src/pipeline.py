"""End-to-end orchestration: one function produces every result shown in the dashboard and exports.

Inspection data -> Validation -> Matching -> Growth & uncertainty -> Readiness -> Prioritisation.
The dashboard, the CSV export and the PDF Evidence Passport all read the same `AnalysisResult`,
which is how they are kept consistent.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from . import __version__
from .assessment import assess_readiness, readiness_summary
from .matching import MatchResult, match_runs
from .prediction import compute_growth
from .prioritization import prioritize
from .schema import AnalysisConfig
from .uncertainty import ShrinkageFit
from .validation import ValidationResult, validate


@dataclass
class SourceInfo:
    name: str                 # e.g. "Demo dataset (synthetic)" or uploaded file names
    files: list[str]
    synthetic: bool
    pipeline_length_m: float | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    source: SourceInfo
    config: AnalysisConfig
    fingerprint: str
    created_utc: str
    validation: ValidationResult
    match: MatchResult | None
    growth: pd.DataFrame | None
    shrinkage: ShrinkageFit | None
    readiness: pd.DataFrame | None
    priorities: pd.DataFrame | None
    issues: pd.DataFrame
    findings: pd.DataFrame | None
    software_version: str = __version__
    evaluation: dict | None = None

    @property
    def ok(self) -> bool:
        return self.match is not None

    def summary(self) -> dict:
        if not self.ok:
            return {}
        d = self.validation.data
        m = self.match
        sub = d[d["run_id"].isin([m.run_a, m.run_b])]
        cats = self.priorities["review_category"].value_counts().to_dict()
        return dict(
            pipeline_ids=sorted(sub["pipeline_id"].dropna().astype(str).unique().tolist()),
            run_a=m.run_a, run_b=m.run_b,
            date_a=m.date_a.strftime("%Y-%m-%d"), date_b=m.date_b.strftime("%Y-%m-%d"),
            years_between=round(m.years_between, 3),
            n_records_a=int((sub["run_id"] == m.run_a).sum()), n_records_b=int((sub["run_id"] == m.run_b).sum()),
            n_segments=int(sub["segment_id"].nunique()),
            n_findings=int(len(self.findings)),
            match_counts=m.status_counts(),
            issue_counts=_sev_counts(self.issues),
            review_counts=cats,
            readiness=readiness_summary(self.readiness),
        )


def _sev_counts(iss: pd.DataFrame) -> dict:
    c = iss["severity"].value_counts().to_dict() if len(iss) else {}
    return {k: int(c.get(k, 0)) for k in ("Error", "Warning", "Info")}


def fingerprint(df: pd.DataFrame) -> str:
    """SHA-256 of the canonical CSV text of the source data (traceability of the evidence)."""
    return hashlib.sha256(df.to_csv(index=False).encode("utf-8")).hexdigest()


def available_runs(df_raw: pd.DataFrame) -> pd.DataFrame:
    if "run_id" not in df_raw.columns or "inspection_date" not in df_raw.columns:
        return pd.DataFrame(columns=["run_id", "inspection_date", "records"])
    t = df_raw.assign(_d=pd.to_datetime(df_raw["inspection_date"], errors="coerce"))
    g = t.groupby("run_id").agg(inspection_date=("_d", "min"), records=("run_id", "size")).reset_index()
    return g.sort_values("inspection_date").reset_index(drop=True)


def run_analysis(df_raw: pd.DataFrame, source: SourceInfo, config: AnalysisConfig | None = None,
                 run_a: str | None = None, run_b: str | None = None) -> AnalysisResult:
    cfg = config or AnalysisConfig()
    fp = fingerprint(df_raw)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    v = validate(df_raw, cfg, source.pipeline_length_m)
    if v.blocking:
        return AnalysisResult(source, cfg, fp, created, v, None, None, None, None, None, v.issues, None)

    runs = available_runs(df_raw)
    runs = runs[runs["inspection_date"].notna()]
    if run_a is None or run_b is None:
        if len(runs) < 2:
            iss = pd.concat([v.issues, pd.DataFrame([dict(
                issue_id="V999", severity="Error", code="FEWER_THAN_TWO_RUNS", run_id=None, observation_id=None,
                field="run_id", value=str(len(runs)),
                message="At least two inspection runs with valid dates are needed for comparison.",
                effect="Matching and growth cannot run.", action="Upload a second inspection run.")])],
                ignore_index=True)
            return AnalysisResult(source, cfg, fp, created, v, None, None, None, None, None, iss, None)
        run_a, run_b = runs["run_id"].iloc[-2], runs["run_id"].iloc[-1]
    if run_a == run_b:
        raise ValueError("Select two different inspection runs.")

    m = match_runs(v.data, run_a, run_b, cfg)
    G, fit, extra = compute_growth(v.data, m, cfg)
    R = assess_readiness(G)
    P = prioritize(G, cfg, m.run_a, m.run_b)

    issues = v.issues.copy()
    if extra:
        e = pd.DataFrame(extra)
        start = len(issues)
        e.insert(0, "issue_id", [f"V{start + i + 1:03d}" for i in range(len(e))])
        issues = pd.concat([issues, e], ignore_index=True)

    F = G.merge(R, on="track_id", how="left").merge(P, on="track_id", how="left")
    F = F.sort_values("priority_order").reset_index(drop=True)
    return AnalysisResult(source, cfg, fp, created, v, m, G, fit, R, P, issues, F)


def attach_evaluation(result: AnalysisResult, ground_truth: pd.DataFrame) -> AnalysisResult:
    """Post-hoc evaluation on synthetic data only. Called after the analysis is complete."""
    from .evaluation import evaluate_growth, evaluate_matching
    if not result.ok:
        return result
    m = result.match
    result.evaluation = dict(
        matching=evaluate_matching(m.tracks, ground_truth, m.run_a, m.run_b),
        growth=evaluate_growth(result.growth, ground_truth, m.run_a, m.run_b, result.config.noise_k),
    )
    return result

