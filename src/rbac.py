"""Central role and permission model (role-based access control).

* Four stakeholder roles. User administration is a SEPARATE capability (account flag `is_admin`), not a fifth role
  and not implied by the manager role.
* `CAPABILITIES` maps each protected action to the roles allowed to perform it; `PAGE_ACCESS` maps each page to the
  roles that see it. Both can be overridden per organisation with a JSON file (CORROSIGHT_PERMISSIONS, default
  `instance/permissions.json`), e.g. {"capabilities": {"upload_data": ["analyst"]}, "pages": {"strategy": ["planner"]}}.
* `require()` is called by src/actions.py before every protected operation, so hiding a button is never the only
  control. `can()` is used by the UI to disable controls and explain why.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ROLES = {
    "engineer": dict(title="Pipeline Integrity Engineer",
                     purpose="Review findings, understand engineering evidence and record review decisions."),
    "analyst": dict(title="Inspection Data Analyst",
                    purpose="Prepare, validate and investigate inspection data."),
    "planner": dict(title="Maintenance & Inspection Planner",
                    purpose="Plan additional investigations and allocate hypothetical or verified resources."),
    "manager": dict(title="Pipeline Operator / Asset Integrity Manager",
                    purpose="Oversee the integrity workflow and review documented findings and decisions."),
}
ALL = list(ROLES)

# capability -> (description, default roles)
CAPABILITIES = {
    "view_overview": ("View overview, findings and evidence pages", ALL),
    "load_shared_dataset": ("Load the shared / demo dataset into a session", ALL),
    "upload_data": ("Upload new inspection data", ["engineer", "analyst"]),
    "change_analysis_settings": ("Change analysis thresholds and apply What-If scenarios", ["engineer", "analyst"]),
    "propose_correction": ("Propose a measurement correction (original kept)", ["engineer", "analyst"]),
    "propose_match_resolution": ("Propose a defect identity resolution", ["engineer", "analyst"]),
    "record_review": ("Record an engineering review decision", ["engineer"]),
    "reopen_review": ("Reopen a review", ["engineer"]),
    "save_snapshot": ("Save an analysis snapshot", ["engineer", "analyst"]),
    "replay_snapshot": ("Replay and compare analysis snapshots", ALL),
    "create_planning_scenario": ("Create planning scenarios (strategy simulator, budget planner)", ["engineer", "planner"]),
    "export_evidence": ("Export the Evidence Passport and findings data", ["engineer", "analyst", "manager"]),
    "export_planning": ("Export planning summaries", ["engineer", "planner", "manager"]),
    "view_audit": ("View authorised audit records", ALL),
    "use_assistant": ("Ask the evidence-grounded assistant", ALL),
    # administrator-only capabilities (granted by the account's is_admin flag, never by role)
    "manage_users": ("Create, update, deactivate users and reset passwords", []),
    "change_system_config": ("Change system configuration / permissions", []),
}
ADMIN_CAPABILITIES = {"manage_users", "change_system_config"}

PAGE_ACCESS = {
    "home": ALL, "account": ALL,
    "overview": ALL, "health": ALL,
    "history": ["engineer", "analyst", "manager"],
    "timeline": ALL,
    "identity": ALL,
    "anomalies": ["engineer", "analyst", "planner", "manager"],
    "patterns": ["engineer", "analyst"],
    "forecast": ALL,
    "whatif": ALL,
    "arena": ALL,
    "contradictions": ALL,
    "strategy": ["engineer", "planner", "manager"],
    "workbench": ALL,
    "gaps": ALL,
    "planning": ["engineer", "planner", "manager"],
    "trust": ALL,
    "assistant": ALL,
    "snapshots": ["engineer", "analyst", "manager"],
    "passport": ALL,
    "users": [],            # administrators only
}
ADMIN_PAGES = {"users"}


class PermissionDenied(Exception):
    pass


def _overrides() -> dict:
    p = Path(os.environ.get("CORROSIGHT_PERMISSIONS") or ROOT / "instance" / "permissions.json")
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def capability_roles(cap: str) -> list[str]:
    o = _overrides().get("capabilities", {})
    roles = o.get(cap, CAPABILITIES[cap][1]) if cap in CAPABILITIES else []
    return [r for r in roles if r in ROLES]


def page_roles(page: str) -> list[str]:
    o = _overrides().get("pages", {})
    return [r for r in o.get(page, PAGE_ACCESS.get(page, [])) if r in ROLES]


def can(user: dict | None, cap: str) -> bool:
    if not user or user.get("status", "active") != "active":
        return False
    if cap in ADMIN_CAPABILITIES:
        return bool(user.get("is_admin"))
    return user.get("role") in capability_roles(cap)


def can_view(user: dict | None, page: str) -> bool:
    if not user or user.get("status", "active") != "active":
        return False
    if page in ADMIN_PAGES:
        return bool(user.get("is_admin"))
    return user.get("role") in page_roles(page)


def explain(cap: str) -> str:
    desc = CAPABILITIES.get(cap, (cap, []))[0]
    if cap in ADMIN_CAPABILITIES:
        return f"'{desc}' is limited to user administrators."
    allowed = [ROLES[r]["title"] for r in capability_roles(cap)]
    return f"'{desc}' is available to: {', '.join(allowed) or 'no role'}. Your role does not include it."


def require(user: dict | None, cap: str):
    if not can(user, cap):
        raise PermissionDenied(explain(cap) if user else "Sign in required.")


def matrix() -> list[dict]:
    rows = []
    for cap, (desc, _) in CAPABILITIES.items():
        row = {"capability": desc}
        for r, info in ROLES.items():
            row[info["title"]] = ("admin flag" if cap in ADMIN_CAPABILITIES else
                                  "Yes" if r in capability_roles(cap) else "-")
        rows.append(row)
    return rows
