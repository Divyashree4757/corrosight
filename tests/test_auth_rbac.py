"""Authentication, role-based access control and protected actions (backend, no UI)."""

import json

import pytest

from src import actions, rbac
from src.anomalies import CorrectionLog
from src.audit import AuditLog
from src.auth import UserStore, hash_password, password_problems, verify_password
from src.conflicts import RESOLUTION_OPTIONS, ResolutionLog
from src.rbac import PermissionDenied
from src.review import ReviewStore
from src.snapshots import SnapshotStore

PW = "Corrosion2026x"


@pytest.fixture
def store(tmp_path):
    s = UserStore(tmp_path / "users.json")
    for name, role in (("eng", "engineer"), ("ana", "analyst"), ("pla", "planner"), ("man", "manager")):
        s.create_user(name, f"Test {role}", role, PW)
    s.create_user("adm", "Admin", "manager", PW, is_admin=True)
    return s


def user(store, name):
    return store.find(name)


# ------------------------------------------------------------------ authentication
def test_valid_and_invalid_credentials(store):
    assert store.authenticate("eng", PW).ok
    assert store.authenticate("ENG ", PW).ok                      # username is case/space-insensitive
    bad = store.authenticate("eng", "wrongpassword1")
    unknown = store.authenticate("nobody", PW)
    assert not bad.ok and not unknown.ok
    assert bad.message == unknown.message == "Invalid username or password."   # no user enumeration
    assert not store.authenticate("", "").ok


def test_passwords_never_stored_in_plaintext(store):
    raw = store.path.read_text()
    assert PW not in raw and "pbkdf2_sha256$" in raw
    assert all("password_hash" not in u for u in store.list_users())     # public view hides hashes
    h = hash_password(PW, iterations=1000)
    assert verify_password(PW, h) and not verify_password("x" + PW, h)
    assert hash_password(PW, 1000) != h                                     # salted


def test_password_policy_and_no_duplicates(store):
    assert password_problems("short1")
    with pytest.raises(ValueError):
        store.create_user("new", "N", "engineer", "alllettersonly")
    with pytest.raises(ValueError):
        store.create_user("eng", "Dup", "engineer", PW)
    with pytest.raises(ValueError):
        store.create_user("x1", "X", "superuser", PW)


def test_lockout_after_repeated_failures(store):
    for _ in range(5):
        assert not store.authenticate("pla", "wrongpassword1").ok
    r = store.authenticate("pla", PW)
    assert not r.ok and "Too many failed attempts" in r.message


def test_inactive_account_and_password_change(store):
    m = user(store, "man")
    store.update_user(m["user_id"], status="inactive")
    assert "inactive" in store.authenticate("man", PW).message
    store.update_user(m["user_id"], status="active")
    temp = store.reset_password(m["user_id"])
    r = store.authenticate("man", temp)
    assert r.ok and r.user["must_change_password"]
    with pytest.raises(ValueError):
        store.change_own_password(m["user_id"], "notcurrent123", "NewPassword99")
    store.change_own_password(m["user_id"], temp, "NewPassword99")
    assert store.authenticate("man", "NewPassword99").ok and not store.find("man")["must_change_password"]


# ------------------------------------------------------------------ permissions
def test_permission_matrix_defaults(store):
    e, a, p, m, adm = (user(store, n) for n in ("eng", "ana", "pla", "man", "adm"))
    assert rbac.can(e, "record_review") and not rbac.can(a, "record_review") and not rbac.can(p, "record_review") \
        and not rbac.can(m, "record_review")
    assert rbac.can(a, "upload_data") and not rbac.can(p, "upload_data") and not rbac.can(m, "upload_data")
    assert rbac.can(p, "create_planning_scenario") and not rbac.can(m, "create_planning_scenario")
    assert rbac.can(m, "export_evidence") and not rbac.can(p, "export_evidence") and rbac.can(p, "export_planning")
    assert not any(rbac.can(u, "manage_users") for u in (e, a, p, m)) and rbac.can(adm, "manage_users")
    assert rbac.can_view(adm, "users") and not rbac.can_view(m, "users")
    assert rbac.can_view(p, "strategy") and not rbac.can_view(a, "strategy") and not rbac.can_view(p, "patterns")
    assert not rbac.can(None, "view_overview") and not rbac.can_view(None, "overview")
    assert not rbac.can(dict(e, status="inactive"), "record_review")


def test_permissions_are_configurable(tmp_path, store, monkeypatch):
    f = tmp_path / "perm.json"
    f.write_text(json.dumps({"capabilities": {"record_review": ["engineer", "manager"]}, "pages": {"patterns": ["planner"]}}))
    monkeypatch.setenv("CORROSIGHT_PERMISSIONS", str(f))
    assert rbac.can(user(store, "man"), "record_review")
    assert rbac.can_view(user(store, "pla"), "patterns") and not rbac.can_view(user(store, "eng"), "patterns")


# ------------------------------------------------------------------ protected actions (server-side enforcement)
def test_actions_enforce_permissions_and_audit(tmp_path, store, demo_result):
    audit = AuditLog(tmp_path / "audit.json")
    reviews = ReviewStore(tmp_path / "rv.json")
    fp = demo_result.fingerprint
    for name in ("ana", "pla", "man"):
        with pytest.raises(PermissionDenied):
            actions.record_review(user(store, name), audit, reviews, fp, "T0001", "Reviewed", "x", "y", reason="r")
    assert reviews.history(fp) == []                                         # nothing written when denied
    e = actions.record_review(user(store, "eng"), audit, reviews, fp, "T0001", "Reviewed", "x", "y", reason="checked")
    assert e["user_id"] == user(store, "eng")["user_id"] and e["user_role"] == "engineer"
    assert e["reviewer"] == "Test engineer"                                  # identity comes from the session, not a text box
    with pytest.raises(PermissionDenied):
        actions.reopen_review(user(store, "ana"), audit, reviews, fp, "T0001", "x")
    actions.reopen_review(user(store, "eng"), audit, reviews, fp, "T0001", "new evidence")
    ev = audit.load()
    kinds = [x["action"] for x in ev]
    assert kinds.count("access_denied") == 4 and "review_recorded" in kinds and "review_reopened" in kinds
    assert all(x["event_id"].startswith("E-") and x["timestamp_utc"] for x in ev)
    # analyst proposals allowed; planner denied
    corr, res = CorrectionLog(tmp_path / "c.json"), ResolutionLog(tmp_path / "r.json")
    actions.propose_correction(user(store, "ana"), audit, corr, fp, "R2016", "A16-0001", "depth_mm", 1.0, "1.1", "unit")
    actions.propose_resolution(user(store, "ana"), audit, res, fp, "T0163", "a -> b", "Ambiguous match",
                               RESOLUTION_OPTIONS[0], "", "confirmed on raw data")
    with pytest.raises(PermissionDenied):
        actions.propose_correction(user(store, "pla"), audit, corr, fp, "R2016", "A16-0001", "depth_mm", 1.0, "1.1", "x")
    assert corr.load()[0]["user_role"] == "analyst" and res.load()[0]["user_role"] == "analyst"
    # snapshots: manager may replay but not save
    snaps = SnapshotStore(tmp_path / "s.json")
    with pytest.raises(PermissionDenied):
        actions.save_snapshot(user(store, "man"), audit, snaps, demo_result, {}, "x")
    s = actions.save_snapshot(user(store, "ana"), audit, snaps, demo_result, {}, "baseline")
    actions.snapshot_event(user(store, "man"), audit, "snapshot_replayed", s["snapshot_id"], fp)
    # exports
    with pytest.raises(PermissionDenied):
        actions.export(user(store, "pla"), audit, "PDF Evidence Passport", "f.pdf", fp)
    actions.export(user(store, "pla"), audit, "Strategy CSV", "s.csv", fp, planning=True)
    with pytest.raises(PermissionDenied):
        actions.load_dataset(user(store, "man"), audit, True, "upload", ["a.csv"], fp)
    actions.load_dataset(user(store, "man"), audit, False, "demo", ["d.csv"], fp)


def test_admin_user_management(tmp_path, store):
    audit = AuditLog(tmp_path / "audit.json")
    adm, man = user(store, "adm"), user(store, "man")
    with pytest.raises(PermissionDenied):
        actions.admin_create_user(man, audit, store, username="new1", display_name="N", role="planner", password=PW)
    u = actions.admin_create_user(adm, audit, store, username="new1", display_name="N", role="planner", password=PW)
    assert u["must_change_password"]
    actions.admin_update_user(adm, audit, store, u["user_id"], role="analyst")
    actions.admin_update_user(adm, audit, store, u["user_id"], status="inactive")
    temp = actions.admin_reset_password(adm, audit, store, u["user_id"])
    assert temp not in store.path.read_text()
    with pytest.raises(ValueError):
        actions.admin_update_user(adm, audit, store, adm["user_id"], status="inactive")
    kinds = [x["action"] for x in audit.load()]
    assert {"user_created", "role_changed", "user_deactivated", "password_reset", "access_denied"} <= set(kinds)


def test_seed_from_hashed_records_only_when_empty(tmp_path, store):
    empty = UserStore(tmp_path / "fresh.json")
    h = hash_password(PW, iterations=1000)
    n = empty.seed_from_records([{"username": "Cloud.Eng", "role": "engineer", "password_hash": h, "display_name": "Cloud Engineer"},
                                 {"username": "boss", "role": "manager", "password_hash": h, "is_admin": True}])
    assert n == 2 and empty.authenticate("cloud.eng", PW).ok and empty.find("boss")["is_admin"]
    assert PW not in empty.path.read_text()
    assert empty.seed_from_records([{"username": "x1x", "role": "planner", "password_hash": h}]) == 0   # never overwrites
    with pytest.raises(ValueError):
        UserStore(tmp_path / "bad.json").seed_from_records([{"username": "plain", "role": "engineer", "password_hash": PW}])
