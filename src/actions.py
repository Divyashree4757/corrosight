"""Protected operations. Every consequential action in the UI goes through this module, which (1) checks the
signed-in user's permission on the server (rbac.require), (2) performs the action, and (3) writes a user-attributed
audit event only after it succeeded. A denied attempt raises PermissionDenied and is itself audited.

The UI also disables controls a role may not use, but these checks are the enforcement.
"""

from __future__ import annotations

from .audit import AuditLog
from .auth import UserStore
from .rbac import PermissionDenied, require


def _guard(actor, cap, audit: AuditLog, resource=""):
    try:
        require(actor, cap)
    except PermissionDenied:
        if actor:
            audit.record(actor, "access_denied", resource, f"capability: {cap}")
        raise


# ---------------------------------------------------------------- data and analysis
def load_dataset(actor, audit: AuditLog, uploaded: bool, name: str, files: list[str], dataset_fp: str):
    _guard(actor, "upload_data" if uploaded else "load_shared_dataset", audit, name)
    audit.record(actor, "dataset_uploaded" if uploaded else "dataset_loaded", name, ", ".join(files), dataset_fp)


def change_settings(actor, audit: AuditLog, old: dict, new: dict, dataset_fp: str = ""):
    _guard(actor, "change_analysis_settings", audit, "analysis settings")
    diff = "; ".join(f"{k}: {old.get(k)} -> {v}" for k, v in new.items() if old.get(k) != v) or "reset to defaults"
    audit.record(actor, "settings_changed", "analysis settings", diff, dataset_fp)
    return new


# ---------------------------------------------------------------- analyst / engineer proposals
def propose_correction(actor, audit, store, dataset_fp, run_id, observation_id, field, original, proposed, rationale, flag_id=""):
    _guard(actor, "propose_correction", audit, f"{run_id}/{observation_id}")
    e = store.propose(dataset_fp, run_id, observation_id, field, original, proposed, rationale,
                      actor["display_name"], flag_id, actor=actor)
    audit.record(actor, "correction_proposed", f"{run_id}/{observation_id}", f"{field}: {original} -> {proposed}", dataset_fp)
    return e


def propose_resolution(actor, audit, store, dataset_fp, track_id, pairing, status, resolution, alternative, rationale):
    _guard(actor, "propose_match_resolution", audit, track_id)
    e = store.propose(dataset_fp, track_id, pairing, status, resolution, alternative, rationale, actor["display_name"],
                      actor=actor)
    audit.record(actor, "resolution_proposed", track_id, f"{resolution} {alternative}".strip(), dataset_fp)
    return e


# ---------------------------------------------------------------- engineering decisions
def record_review(actor, audit, store, dataset_fp, track_id, status, reviewer_step, system_step, notes="", reason="",
                  assigned_to="", snapshot_id=""):
    _guard(actor, "record_review", audit, track_id)
    e = store.record(dataset_fp, track_id, status, reviewer_step, system_step, actor["display_name"], notes, reason=reason,
                     assigned_to=assigned_to, snapshot_id=snapshot_id, actor=actor)
    audit.record(actor, "review_recorded", track_id, f"{status}; {reason}".strip("; "), dataset_fp)
    return e


def reopen_review(actor, audit, store, dataset_fp, track_id, reason):
    _guard(actor, "reopen_review", audit, track_id)
    e = store.reopen(dataset_fp, track_id, actor["display_name"], reason, actor=actor)
    audit.record(actor, "review_reopened", track_id, reason, dataset_fp)
    return e


# ---------------------------------------------------------------- snapshots and exports
def save_snapshot(actor, audit, store, result, reviews_latest, note):
    _guard(actor, "save_snapshot", audit, "snapshot")
    e = store.save(result, reviews_latest, note, actor["display_name"], actor=actor)
    audit.record(actor, "snapshot_saved", e["snapshot_id"], note, result.fingerprint)
    return e


def snapshot_event(actor, audit, kind: str, resource: str, dataset_fp: str, details: str = ""):
    _guard(actor, "replay_snapshot", audit, resource)
    audit.record(actor, kind, resource, details, dataset_fp)


def export(actor, audit, kind: str, file: str, dataset_fp: str, planning: bool = False):
    _guard(actor, "export_planning" if planning else "export_evidence", audit, kind)
    audit.record(actor, "planning_export" if planning else "export", kind, file, dataset_fp)


def planning_scenario(actor, audit, tool: str, details: str, dataset_fp: str = ""):
    _guard(actor, "create_planning_scenario", audit, tool)
    audit.record(actor, "planning_scenario", tool, details, dataset_fp)


def check(actor, audit, cap: str, resource: str = ""):
    """Permission check for actions that have no store (e.g. running a planning scenario)."""
    _guard(actor, cap, audit, resource)


# ---------------------------------------------------------------- user administration (admin flag only)
def admin_create_user(actor, audit, users: UserStore, **kw):
    _guard(actor, "manage_users", audit, kw.get("username", ""))
    u = users.create_user(must_change_password=True, **kw)
    audit.record(actor, "user_created", u["username"], f"role {u['role']}{', admin' if u['is_admin'] else ''}")
    return u


def admin_update_user(actor, audit, users: UserStore, user_id: str, **changes):
    _guard(actor, "manage_users", audit, user_id)
    before = users.get(user_id)
    if before is None:
        raise ValueError("User not found.")
    if user_id == actor["user_id"] and (changes.get("status") == "inactive" or changes.get("is_admin") is False):
        raise ValueError("You cannot deactivate yourself or remove your own administrator capability.")
    u = users.update_user(user_id, **changes)
    if "role" in changes and changes["role"] != before["role"]:
        audit.record(actor, "role_changed", u["username"], f"{before['role']} -> {u['role']}")
    if "status" in changes and changes["status"] != before["status"]:
        audit.record(actor, "user_deactivated" if changes["status"] == "inactive" else "user_activated", u["username"])
    other = {k: v for k, v in changes.items() if k not in ("role", "status") and before.get(k) != v}
    if other:
        audit.record(actor, "user_updated", u["username"], ", ".join(f"{k} changed" for k in other))
    return u


def admin_reset_password(actor, audit, users: UserStore, user_id: str) -> str:
    _guard(actor, "manage_users", audit, user_id)
    u = users.get(user_id)
    if u is None:
        raise ValueError("User not found.")
    temp = users.reset_password(user_id)
    audit.record(actor, "password_reset", u["username"], "temporary password issued; change required at next sign-in")
    return temp
