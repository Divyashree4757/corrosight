"""Reproducible Analysis Snapshots.

A snapshot records everything needed to say what produced a result: source-data SHA-256, selected runs, the full
AnalysisConfig (matching, validation, forecasting and prioritisation settings), software and algorithm versions,
git commit when available, a digest of the findings table, compact per-finding results and the review decisions
known at that time. Snapshots are appended, never overwritten.

Replay: if the currently loaded data has the same SHA-256, the analysis is re-run with the stored configuration
and runs, and the new findings digest is compared with the stored one ("exact replay verified" only when equal).
The raw data itself is not stored in the snapshot, so replay requires the same dataset to be loaded.
"""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import ALGORITHM_VERSIONS, __version__
from .logstore import JsonLog

ROOT = Path(__file__).resolve().parents[1]


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=3)
        return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else "not available (not a git checkout)"
    except Exception:
        return "not available (git not installed)"


def findings_digest(result) -> str:
    from .reporting import findings_frame
    return hashlib.sha256(findings_frame(result).to_csv(index=False).encode("utf-8")).hexdigest()


def compact_findings(result) -> dict:
    F = result.findings
    out = {}
    for r in F.itertuples():
        out[r.track_id] = [r.review_category, None if not np.isfinite(r.rate_mm_per_yr) else round(float(r.rate_mm_per_yr), 6),
                           r.match_status, r.forecast_status,
                           None if not np.isfinite(r.proj_depth_upper_mm) else round(float(r.proj_depth_upper_mm), 6)]
    return out


class SnapshotStore(JsonLog):
    def save(self, result, reviews_latest: dict, note: str = "", created_by: str = "", actor: dict | None = None) -> dict:
        s = result.summary()
        ts = datetime.now(timezone.utc)
        digest = findings_digest(result)
        sid = f"SNAP-{ts:%Y%m%d-%H%M%S}-{digest[:6]}"
        entry = dict(
            snapshot_id=sid, dataset_fingerprint=result.fingerprint, timestamp_utc=ts.strftime("%Y-%m-%d %H:%M:%S UTC"),
            note=note.strip(), created_by=created_by.strip() or "(not given)",
            user_id=(actor or {}).get("user_id", ""), user_role=(actor or {}).get("role", ""),
            source=dict(name=result.source.name, files=result.source.files, synthetic=result.source.synthetic,
                        pipeline_length_m=result.source.pipeline_length_m),
            runs=dict(run_a=s["run_a"], run_b=s["run_b"], date_a=s["date_a"], date_b=s["date_b"]),
            config=result.config.to_dict(), software_version=__version__, algorithm_versions=dict(ALGORITHM_VERSIONS),
            git_commit=git_commit(), findings_digest=digest,
            summary=dict(match_counts=s["match_counts"], review_counts=s["review_counts"], issue_counts=s["issue_counts"],
                         n_findings=s["n_findings"]),
            findings=compact_findings(result),
            reviews={k: dict(status=v.get("status"), reviewer=v.get("reviewer"), timestamp_utc=v.get("timestamp_utc"))
                     for k, v in reviews_latest.items()},
            replay_requirements=["The same source data (matching SHA-256) must be loaded; raw data is not stored in the snapshot."],
        )
        return self.append(entry)

    def list(self, dataset_fp: str | None = None) -> list[dict]:
        log = self.load()
        return [e for e in log if dataset_fp is None or e["dataset_fingerprint"] == dataset_fp]

    def get(self, snapshot_id: str) -> dict | None:
        return next((e for e in self.load() if e["snapshot_id"] == snapshot_id), None)


def replay(snapshot: dict, raw_df: pd.DataFrame, source, run_fn) -> dict:
    """Re-run a snapshot on the loaded data. run_fn(raw, source, config, run_a, run_b) -> AnalysisResult."""
    from .pipeline import fingerprint
    from .schema import AnalysisConfig
    fp = fingerprint(raw_df)
    missing = []
    if fp != snapshot["dataset_fingerprint"]:
        missing.append("Loaded data differs from the snapshot's source data (SHA-256 mismatch).")
        return dict(status="Cannot replay", exact=False, missing=missing, differences=[])
    known = AnalysisConfig().to_dict().keys()
    cfg = AnalysisConfig(**{k: v for k, v in snapshot["config"].items() if k in known})
    res = run_fn(raw_df, source, cfg, snapshot["runs"]["run_a"], snapshot["runs"]["run_b"])
    new_digest = findings_digest(res)
    diffs = []
    if snapshot["algorithm_versions"] != ALGORITHM_VERSIONS:
        diffs.append("Algorithm versions differ from those recorded.")
    old, new = snapshot["findings"], compact_findings(res)
    changed = [t for t in set(old) | set(new) if old.get(t) != new.get(t)]
    if changed:
        diffs.append(f"{len(changed)} finding(s) differ, e.g. {', '.join(sorted(changed)[:8])}")
    exact = new_digest == snapshot["findings_digest"]
    return dict(status="Exact replay verified" if exact else "Replay differs", exact=exact, missing=missing,
                differences=diffs, new_digest=new_digest, result=res)


def compare(a: dict, b: dict) -> dict:
    """What changed from snapshot a to snapshot b."""
    meta = []
    for label, ka in (("Source data SHA-256", "dataset_fingerprint"), ("Software version", "software_version"),
                      ("Git commit", "git_commit"), ("Findings digest", "findings_digest")):
        if a.get(ka) != b.get(ka):
            meta.append(dict(item=label, before=str(a.get(ka))[:20], after=str(b.get(ka))[:20]))
    if a.get("runs") != b.get("runs"):
        meta.append(dict(item="Runs compared", before=f"{a['runs']['run_a']}->{a['runs']['run_b']}",
                         after=f"{b['runs']['run_a']}->{b['runs']['run_b']}"))
    for k in sorted(set(a.get("algorithm_versions", {})) | set(b.get("algorithm_versions", {}))):
        va, vb = a.get("algorithm_versions", {}).get(k), b.get("algorithm_versions", {}).get(k)
        if va != vb:
            meta.append(dict(item=f"Algorithm: {k}", before=str(va), after=str(vb)))
    cfg = [dict(setting=k, before=a["config"].get(k), after=b["config"].get(k))
           for k in sorted(set(a["config"]) | set(b["config"])) if a["config"].get(k) != b["config"].get(k)]
    fa, fb = a.get("findings", {}), b.get("findings", {})
    rows = []
    for t in sorted(set(fa) | set(fb)):
        x, y = fa.get(t), fb.get(t)
        if x != y:
            rows.append(dict(track_id=t, category_before=x[0] if x else "(absent)", category_after=y[0] if y else "(absent)",
                             rate_before=x[1] if x else None, rate_after=y[1] if y else None,
                             forecast_before=x[3] if x else None, forecast_after=y[3] if y else None))
    rv = []
    ra, rb = a.get("reviews", {}), b.get("reviews", {})
    for t in sorted(set(ra) | set(rb)):
        if ra.get(t, {}).get("status") != rb.get(t, {}).get("status"):
            rv.append(dict(track_id=t, before=ra.get(t, {}).get("status", "(none)"), after=rb.get(t, {}).get("status", "(none)")))
    return dict(metadata=pd.DataFrame(meta), config=pd.DataFrame(cfg), findings=pd.DataFrame(rows), reviews=pd.DataFrame(rv))
