"""User-attributed, append-only audit log (outputs/audit_log.json by default).

Each event: event_id, timestamp_utc, user_id, username, user_role (at the time of the event), action, resource,
dataset_fingerprint (when relevant), details. Events are written only after the action succeeded; failed sign-ins
are recorded with the attempted username only (never a password).
"""

from __future__ import annotations

import uuid

from .logstore import JsonLog

ACTIONS = {
    "login": "Signed in", "login_failed": "Failed sign-in", "logout": "Signed out", "session_expired": "Session expired",
    "password_changed": "Password changed", "dataset_loaded": "Dataset loaded", "dataset_uploaded": "Dataset uploaded",
    "settings_changed": "Analysis settings changed", "correction_proposed": "Correction proposed",
    "resolution_proposed": "Match resolution proposed", "review_recorded": "Review decision recorded",
    "review_reopened": "Review reopened", "snapshot_saved": "Snapshot saved", "snapshot_replayed": "Snapshot replayed",
    "snapshot_compared": "Snapshots compared", "export": "Evidence exported", "planning_export": "Planning summary exported",
    "planning_scenario": "Planning scenario run",
    "user_created": "User created", "user_updated": "User updated", "role_changed": "Role changed",
    "user_deactivated": "User deactivated", "user_activated": "User activated", "password_reset": "Password reset by admin",
    "access_denied": "Action denied",
}


class AuditLog(JsonLog):
    def record(self, actor: dict | None, action: str, resource: str = "", details: str = "", dataset_fp: str = "") -> dict:
        a = actor or {}
        return self.append(dict(event_id=f"E-{uuid.uuid4().hex[:12]}", user_id=a.get("user_id", ""),
                                username=a.get("username", ""), user_role=a.get("role", ""), action=action,
                                action_label=ACTIONS.get(action, action), resource=resource, details=details,
                                dataset_fingerprint=dataset_fp))
