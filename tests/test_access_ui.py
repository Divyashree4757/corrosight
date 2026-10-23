"""UI-level access control: sign-in gate, role navigation, page guards, sign-out and session isolation."""

from html import escape

from streamlit.testing.v1 import AppTest

from src.audit import AuditLog
from src.auth import UserStore
from test_app import APP, PW, fresh, load_demo, login, texts

import ui_core as U



def sidebar_text(at):
    return " ".join(m.value for m in at.sidebar.markdown)


def test_unauthenticated_user_sees_only_sign_in():
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["_nav_default"] = "workbench"        # deep link attempt before sign-in
    at.run()
    html = texts(at)
    assert "Welcome back" in html and "Sign in to access your pipeline inspection workspace." in html
    assert "Engineering Review Workbench" not in html and "raw_csv" not in at.session_state
    assert [b.label for b in at.button] == ["Sign in"]          # no data controls, no navigation actions
    pw = [t for t in at.text_input if t.key == "login_pw"][0]
    assert pw.proto.type == pw.proto.PASSWORD                    # masked by default (browser shows an eye toggle)


def test_invalid_credentials_rejected_without_detail():
    at = AppTest.from_file(APP, default_timeout=180).run()
    login(at, "eng", "wrongpassword1")
    assert any(e.value == "Invalid username or password." for e in at.error)
    login(at, "nobody", PW)
    assert any(e.value == "Invalid username or password." for e in at.error)
    login(at, "", "")
    assert any("Enter your username and password" in e.value for e in at.error)
    assert "auth" not in at.session_state and "Welcome back" in texts(at)
    assert all("wrongpassword1" not in str(e) for e in U.audit_log().load())   # passwords never logged


def test_lockout_after_repeated_failures_in_ui():
    at = AppTest.from_file(APP, default_timeout=180).run()
    for _ in range(5):
        login(at, "locked", "wrongpassword1")
    login(at, "locked", PW)
    assert any("Too many failed attempts" in e.value for e in at.error)
    assert "auth" not in at.session_state


def test_each_role_gets_its_own_home_and_navigation():
    expect = {
        "eng": ("Pipeline Integrity Engineer", "Review first"),
        "ana": ("Inspection Data Analyst", "Validation errors"),
        "pla": ("Maintenance & Inspection Planner", "Outstanding reviews"),
        "man": ("Pipeline Operator / Asset Integrity Manager", "Review progress"),
    }
    for user, (title, kpi) in expect.items():
        at = load_demo(fresh("home", user))
        html = texts(at)
        assert escape(title) in html and kpi in html, user
        assert escape(title) in sidebar_text(at)                          # role shown in the sidebar user card
        assert any(b.label == "Sign out" for b in at.sidebar.button)
        assert set(U.NAV) and "users" not in U.NAV                # no admin page for non-admins
    # page registration by role
    at = fresh("home", "ana")
    assert "patterns" in U.NAV and "strategy" not in U.NAV and "planning" not in U.NAV
    at = fresh("home", "pla")
    assert "strategy" in U.NAV and "patterns" not in U.NAV and "snapshots" not in U.NAV


def test_forbidden_page_cannot_be_opened_by_deep_link():
    at = load_demo(fresh("strategy", "ana"))                     # analysts have no strategy simulator
    assert "Inspection Strategy Simulator" not in [m.value for m in at.markdown if m.value.startswith("## ")]
    assert "Welcome, Test analyst" in texts(at)
    at = fresh("users", "man")                                   # manager is not automatically an administrator
    assert "## User management" not in texts(at)


def test_admin_page_only_for_admin_and_creates_user():
    at = fresh("users", "adm")
    assert "users" in U.NAV and "## User management" in texts(at)
    [t for t in at.text_input if t.label == "Username"][0].input("newplanner")
    [t for t in at.text_input if t.label == "Display name"][0].input("New Planner")
    [b for b in at.button if b.label == "Create user"][0].click().run()
    assert not at.exception, at.exception
    assert any("Created 'newplanner'" in s.value for s in at.success)
    u = UserStore().find("newplanner")
    assert u and u["must_change_password"] and u["role"] == "engineer"   # first role in the list, as selected
    assert any(e["action"] == "user_created" and e["username"] == "adm" for e in AuditLog(U.AUDIT_LOG).load())


def test_role_restrictions_are_enforced_in_the_ui():
    at = load_demo(fresh("planning", "pla"))
    rec = [b for b in at.button if "Record review decision" in (b.label or "")][0]
    assert rec.disabled                                          # planner cannot record engineering decisions
    assert at.button(key="pp_gen").disabled
    assert "dl_csv" not in [b.key for b in at.get("download_button")]   # export bytes never sent to this role
    at = load_demo(fresh("planning", "man"))
    assert at.button(key="pl_run").disabled                      # manager cannot create planning scenarios
    assert not at.button(key="pp_gen").disabled                  # but can export evidence
    radios = [r for r in at.sidebar.radio if r.key == "mode"][0]
    assert radios.options == ["Demo dataset"]                    # no upload option for the manager


def test_review_is_attributed_to_signed_in_user():
    at = load_demo(fresh("workbench", "eng"))
    [t for t in at.text_area if t.label == "Reason for this decision"][0].input("checked sizing")
    [b for b in at.button if "Record review decision" in (b.label or "")][0].click().run()
    assert any("by Test engineer" in s.value for s in at.success)
    assert not [t for t in at.text_input if "Reviewer" in (t.label or "")]   # no free-text identity
    ev = [e for e in AuditLog(U.AUDIT_LOG).load() if e["action"] == "review_recorded"][-1]
    assert ev["username"] == "eng" and ev["user_role"] == "engineer" and ev["event_id"].startswith("E-")
    last = U.review_store().history(ev["dataset_fingerprint"])[-1]
    assert last["reviewer"] == "Test engineer" and last["user_role"] == "engineer" and last["user_id"] == ev["user_id"]


def test_sign_out_clears_session_and_next_user_starts_clean():
    at = load_demo(fresh("assistant", "eng"))
    at.chat_input[0].set_value("Why was T0177 prioritised?").run()
    assert at.session_state["chat"]
    [b for b in at.sidebar.button if b.label == "Sign out"][0].click().run()
    assert "auth" not in at.session_state and "raw_csv" not in at.session_state and "chat" not in at.session_state
    assert "Welcome back" in texts(at) and "You have been signed out." in " ".join(i.value for i in at.info)
    at.run()                                                      # refresh the element tree (AppTest on Streamlit 1.50)
    login(at, "man")                                              # second user in the same browser session
    assert at.session_state["auth_user"]["username"] == "man" and "Test manager" in sidebar_text(at)
    assert "Why was T0177 prioritised?" not in texts(at)          # previous user's chat is gone
    assert "raw_csv" not in at.session_state and "chat" not in at.session_state and "Test engineer" not in sidebar_text(at)


def test_deactivated_account_is_signed_out_on_next_action():
    at = fresh("home", "gone")
    assert "Welcome, Test planner" in texts(at)
    store = UserStore()
    store.update_user(store.find("gone")["user_id"], status="inactive")
    at.run()
    assert "auth" not in at.session_state and "Welcome back" in texts(at)
    login(at, "gone")
    assert any("inactive" in e.value for e in at.error)


def test_expired_session_requires_sign_in_again():
    at = fresh("home", "pla")
    at.session_state["auth"] = dict(at.session_state["auth"], last_seen=0)
    at.run()
    assert "auth" not in at.session_state and "Welcome back" in texts(at)
    assert "expired" in " ".join(i.value for i in at.info)
