"""Human-review log (Evidence-to-Action loop).

* Append-only JSON log stored on disk (default: outputs/review_log.json), so decisions survive restarts.
* Entries are keyed by the dataset fingerprint, so reviews of one dataset never leak into another.
* The system's PROPOSED next step and the reviewer's SELECTED next step are stored separately.
* Recording a status never approves a repair, a work order or an operating change. CorroSight has no
  "approved" status by design: approval happens outside the tool, by qualified people.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

# Engineering Review Workbench statuses (current). None of them means "repaired" or "approved".
WORKBENCH_STATUSES = [
    "Awaiting Review",
    "Additional Evidence Required",
    "Under Review",
    "Reviewed",
    "Closed with Documented Rationale",
]
# Statuses written by earlier versions remain valid so existing review logs keep loading.
LEGACY_STATUSES = [
    "Not reviewed",
    "Awaiting review",
    "Requires further assessment",
    "Match verification requested",
    "Additional data requested",
    "Considered by qualified reviewer",
]
REVIEW_STATUSES = WORKBENCH_STATUSES + LEGACY_STATUSES
CLOSED_STATUS = "Closed with Documented Rationale"

_lock = threading.Lock()


class ReviewStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def record(self, dataset_fp: str, track_id: str, status: str, reviewer_next_step: str,
               system_next_step: str, reviewer: str = "", notes: str = "", reason: str = "",
               assigned_to: str = "", action: str = "recorded", snapshot_id: str = "", actor: dict | None = None) -> dict:
        if status not in REVIEW_STATUSES:
            raise ValueError(f"Unknown review status: {status}")
        if status == CLOSED_STATUS and not reason.strip():
            raise ValueError("Closing a review requires a documented rationale (reason).")
        entry = dict(
            dataset_fingerprint=dataset_fp, track_id=track_id, status=status, action=action,
            system_proposed_next_step=system_next_step, reviewer_selected_next_step=reviewer_next_step,
            reviewer=reviewer.strip() or "(not given)", notes=notes.strip(), reason=reason.strip(),
            assigned_to=assigned_to.strip(), snapshot_id=snapshot_id,
            user_id=(actor or {}).get("user_id", ""), user_role=(actor or {}).get("role", ""),
            timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            approval_note=("Status recorded only. CorroSight does not approve repairs, work orders or operating changes; "
                           "closing a review does not mean a defect was repaired."),
        )
        with _lock:
            log = self._load()
            log.append(entry)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(log, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        return entry

    def history(self, dataset_fp: str, track_id: str | None = None) -> list[dict]:
        return [e for e in self._load() if e["dataset_fingerprint"] == dataset_fp
                and (track_id is None or e["track_id"] == track_id)]

    def reopen(self, dataset_fp: str, track_id: str, reviewer: str, reason: str, actor: dict | None = None) -> dict:
        """Reopen a finding: appends an 'Under Review' entry; earlier decisions stay in the log."""
        prev = self.latest(dataset_fp).get(track_id)
        if prev is None:
            raise ValueError("Nothing to reopen: no review recorded for this finding.")
        return self.record(dataset_fp, track_id, "Under Review", prev.get("reviewer_selected_next_step", ""),
                           prev.get("system_proposed_next_step", ""), reviewer, f"Reopened (previous status: {prev['status']})",
                           reason=reason, assigned_to=prev.get("assigned_to", ""), action="reopened", actor=actor)

    def latest(self, dataset_fp: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for e in self.history(dataset_fp):
            out[e["track_id"]] = e
        return out

    def clear_dataset(self, dataset_fp: str) -> int:
        with _lock:
            log = self._load()
            keep = [e for e in log if e["dataset_fingerprint"] != dataset_fp]
            self.path.write_text(json.dumps(keep, indent=1), encoding="utf-8")
        return len(log) - len(keep)
