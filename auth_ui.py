"""Sign-in, session handling, account and user-administration screens for CorroSight.

Session model (Streamlit): authentication state lives in the server-side st.session_state of one browser session. Only
the user id and timestamps are kept there (never the password or its hash). On every rerun the account is re-read from
the user store, so deactivation or a role change takes effect immediately. Sessions expire after IDLE_MINUTES without
activity. Sign-out and sign-in clear the whole session state, so no data, chat or selection carries over between users.
"""

from __future__ import annotations

import os
import secrets
import time
from html import escape

import pandas as pd
import streamlit as st

import ui_core as U
from src import actions as ACT
from src import rbac, theme
from src.auth import UserStore, password_problems
from src.rbac import ROLES, PermissionDenied

IDLE_MINUTES = int(os.environ.get("CORROSIGHT_SESSION_IDLE_MINUTES", "60"))


def user_store() -> UserStore:
    """The account store. On a fresh cloud deployment (no instance/users.json) accounts are seeded once from the
    `corrosight_users` entries in Streamlit secrets, which hold password HASHES only (see docs/DEPLOY.md)."""
    store = UserStore()
    if store.is_empty():
        try:
            records = [dict(r) for r in st.secrets.get("corrosight_users", [])]
        except Exception:          # no secrets file locally
            records = []
        if records:
            store.seed_from_records(records)
    return store


def _reset_session(message: str = "", keep: tuple = ()):
    """Remove everything from this browser session (data, selections, chat, exports). `keep` lists harmless keys
    (only the requested landing page) that survive a sign-in."""
    for k in list(st.session_state.keys()):
        if k not in keep:
            del st.session_state[k]
    if message:
        st.session_state["_login_msg"] = message


def session_user() -> dict | None:
    """Return the fresh, active account for this session, or None (expired / signed out / deactivated)."""
    auth = st.session_state.get("auth")
    if not auth:
        st.session_state.pop("auth_user", None)
        return None
    now = time.time()
    u = user_store().get(auth.get("user_id", ""))
    if now - auth.get("last_seen", 0) > IDLE_MINUTES * 60:
        U.audit_log().record(u, "session_expired", "session")
        _reset_session(f"Your session expired after {IDLE_MINUTES} minutes without activity. Please sign in again.")
        return None
    if u is None or u.get("status") != "active":
        _reset_session("Your account is no longer active. Contact your administrator.")
        return None
    auth["last_seen"] = now
    st.session_state["auth_user"] = u
    return u


def logout():
    u = st.session_state.get("auth_user")
    if u:
        U.audit_log().record(u, "logout", "session")
    _reset_session("You have been signed out.")


# ============================================================================ sign-in page
def login_page():
    st.markdown(theme.login_css(), unsafe_allow_html=True)
    left, right = st.columns([1.05, 1], gap="large")
    with left:
        st.markdown(
            "<div class='cs-login-brand'>" + theme.logo_html(46, "2.1rem", "#EAF1F4") +
            "<span class='tag'>Pipeline Integrity Evidence</span>"
            "<h3>Connect inspection evidence, expose uncertainty and record every engineering decision.</h3>"
            "<p>CorroSight compares repeated in-line inspections, explains why findings deserve review, and keeps a "
            "traceable record for the people who decide.</p>"
            "<ul><li>Defect matching across inspection runs</li><li>Explainable review priorities</li>"
            "<li>Role-based review workflow and Evidence Passport</li></ul>"
            + theme.PIPE_SVG + "</div>", unsafe_allow_html=True)
    with right:
        msg = st.session_state.pop("_login_msg", None)
        if msg:
            st.info(msg)
        store = user_store()
        if store.is_empty():
            st.markdown("<div class='cs-login-card'><h2>Welcome back</h2>"
                        "<div class='sub'>Sign in to access your pipeline inspection workspace.</div></div>",
                        unsafe_allow_html=True)
            st.warning("No user accounts are configured yet. An administrator must create the first accounts on the "
                       "server, for example:")
            st.code("python -m src.auth add your.name --role engineer --admin\n# or, for a demo:\npython -m src.auth demo",
                    language="bash")
            return
        with st.form("login_form", clear_on_submit=False):
            st.markdown("<div class='cs-login-card'><h2>Welcome back</h2>"
                        "<div class='sub'>Sign in to access your pipeline inspection workspace.</div></div>",
                        unsafe_allow_html=True)
            username = st.text_input("Username or email", key="login_user", placeholder="e.g. engineer",
                                     autocomplete="username")
            password = st.text_input("Password", type="password", key="login_pw", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
        if submitted:
            if not username.strip() or not password:
                st.error("Enter your username and password.")
                return
            with st.spinner("Verifying credentials..."):
                ident = username
                if "@" in username and store.find(username) is None:
                    match = next((u for u in store.list_users() if (u.get("email") or "").lower() == username.strip().lower()), None)
                    ident = match["username"] if match else username
                result = store.authenticate(ident, password)
            if not result.ok:
                U.audit_log().record({"username": username.strip().lower()[:64]}, "login_failed", "session")
                st.error(result.message)
                return
            _reset_session(keep=("_nav_default",))
            st.session_state["auth"] = dict(user_id=result.user["user_id"], login_at=time.time(), last_seen=time.time(),
                                            session_id=secrets.token_hex(8))
            st.session_state["auth_user"] = result.user
            U.audit_log().record(result.user, "login", "session")
            st.rerun()
        st.caption("Accounts are created by an administrator. There is no self-registration.")
    st.markdown("<div class='cs-login-foot'>CorroSight is a pipeline engineering decision-support system. It does not "
                "certify pipeline safety or approve repairs. Authorised use only.</div>", unsafe_allow_html=True)


# ============================================================================ forced password change
def change_password_form(user: dict, forced: bool):
    with st.form("pw_form"):
        cur = st.text_input("Current password" + (" (temporary)" if forced else ""), type="password",
                            autocomplete="current-password")
        new = st.text_input("New password", type="password", autocomplete="new-password",
                            help="At least 10 characters with at least one letter and one digit.")
        rep = st.text_input("Repeat new password", type="password", autocomplete="new-password")
        ok = st.form_submit_button("Change password", type="primary")
    if ok:
        if new != rep:
            st.error("The new passwords do not match.")
            return
        probs = password_problems(new)
        if probs:
            st.error("Password needs " + ", ".join(probs) + ".")
            return
        try:
            user_store().change_own_password(user["user_id"], cur, new)
        except ValueError as e:
            st.error(str(e))
            return
        U.audit_log().record(user, "password_changed", user["username"])
        st.success("Password changed.")
        if forced:
            st.rerun()


def forced_password_page():
    u = st.session_state.get("auth_user")
    st.markdown(theme.login_css(), unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        st.markdown("<div class='cs-login-card'><h2>Set a new password</h2><div class='sub'>Your account uses a temporary "
                    "password. Choose a new one to continue.</div></div>", unsafe_allow_html=True)
        change_password_form(u, forced=True)
        if st.button("Sign out", key="forced_logout"):
            logout()
            st.rerun()


# ============================================================================ sidebar user card
def sidebar_user_card(user: dict):
    with st.sidebar:
        initials = "".join(w[0] for w in user["display_name"].split()[:2]).upper() or "U"
        admin = " &middot; <span style='color:#F2C57C'>user admin</span>" if user.get("is_admin") else ""
        st.markdown(f"<div class='cs-usercard'><div class='cs-avatar'>{escape(initials)}</div><div>"
                    f"<div class='n'>{escape(user['display_name'])}</div>"
                    f"<div class='r'>{escape(ROLES[user['role']]['title'])}{admin}</div></div></div>",
                    unsafe_allow_html=True)
        if st.button("Sign out", key="logout_btn", icon=":material/logout:", width="stretch"):
            logout()
            st.rerun()


# ============================================================================ account page (every role)
def page_account(res=None):
    u = st.session_state.get("auth_user")
    U.topbar("My account", None)
    st.markdown("## My account")
    c = st.columns(3)
    U.kpi(c[0], "Signed in as", escape(u["display_name"]), escape(u["username"]), hi=True)
    U.kpi(c[1], "Role", f"<span style='font-size:1.05rem'>{escape(ROLES[u['role']]['title'])}</span>",
          escape(ROLES[u["role"]]["purpose"]))
    U.kpi(c[2], "Last sign-in", f"<span style='font-size:1.05rem'>{u.get('last_login_utc') or '-'}</span>",
          "user administration" if u.get("is_admin") else "")
    st.markdown("##### What your role can do")
    rows = [dict(action=desc, allowed="Yes" if rbac.can(u, cap) else "No")
            for cap, (desc, _) in rbac.CAPABILITIES.items()]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.caption("No role authorises repairs, operating changes or safety certification; those are outside CorroSight.")
    st.markdown("##### Change password")
    change_password_form(u, forced=False)


# ============================================================================ user administration (admin flag)
def page_users(res=None):
    actor = st.session_state.get("auth_user")
    U.topbar("User management", None)
    st.markdown("## User management")
    st.markdown("<div class='cs-desc'>Create accounts, assign one of the four stakeholder roles, activate or deactivate "
                "access, and issue temporary passwords. Every change is recorded in the audit log. Available only to "
                "accounts with the user-administration capability.</div>", unsafe_allow_html=True)
    if not rbac.can(actor, "manage_users"):
        st.error(rbac.explain("manage_users"))
        return
    store = user_store()
    audit = U.audit_log()
    users = store.list_users()
    df = pd.DataFrame(users)
    df["role"] = df["role"].map(lambda r: ROLES[r]["title"])
    st.dataframe(df[["username", "display_name", "email", "role", "is_admin", "status", "created_utc", "last_login_utc",
                     "must_change_password"]], width="stretch", hide_index=True)
    t1, t2, t3 = st.tabs(["Create user", "Edit / deactivate", "Permission matrix"])
    with t1:
        with st.form("adm_create", clear_on_submit=True):
            c1, c2 = st.columns(2)
            un = c1.text_input("Username")
            dn = c2.text_input("Display name")
            em = c1.text_input("Email (optional)")
            role = c2.selectbox("Role", list(ROLES), format_func=lambda r: ROLES[r]["title"])
            adm = st.checkbox("Grant user-administration capability")
            go = st.form_submit_button("Create user", type="primary")
        if go:
            from src.auth import generate_password
            temp = generate_password()
            try:
                ACT.admin_create_user(actor, audit, store, username=un, display_name=dn, role=role, password=temp, email=em,
                                      is_admin=adm)
                st.success(f"Created '{un.strip().lower()}'. Temporary password (shown once, hand over securely; the user "
                           f"must change it at first sign-in):")
                st.code(temp)
            except (ValueError, PermissionDenied) as e:
                st.error(str(e))
    with t2:
        pick = st.selectbox("Account", [u["user_id"] for u in users],
                            format_func=lambda i: next(f"{u['username']} ({u['display_name']})" for u in users if u["user_id"] == i))
        u = store.get(pick)
        with st.form(f"adm_edit_{pick}"):
            c1, c2 = st.columns(2)
            dn = c1.text_input("Display name", value=u["display_name"])
            em = c2.text_input("Email", value=u.get("email") or "")
            role = c1.selectbox("Role", list(ROLES), index=list(ROLES).index(u["role"]), format_func=lambda r: ROLES[r]["title"])
            status = c2.selectbox("Status", ["active", "inactive"], index=0 if u["status"] == "active" else 1)
            adm = st.checkbox("User-administration capability", value=bool(u["is_admin"]))
            save = st.form_submit_button("Save changes", type="primary")
        if save:
            try:
                ACT.admin_update_user(actor, audit, store, pick, display_name=dn, email=em, role=role, status=status, is_admin=adm)
                st.success("Saved.")
                st.rerun()
            except (ValueError, PermissionDenied) as e:
                st.error(str(e))
        if st.button("Issue temporary password", key=f"adm_reset_{pick}"):
            try:
                temp = ACT.admin_reset_password(actor, audit, store, pick)
                st.success("Temporary password (shown once; the user must change it at next sign-in):")
                st.code(temp)
            except (ValueError, PermissionDenied) as e:
                st.error(str(e))
    with t3:
        st.dataframe(pd.DataFrame(rbac.matrix()), width="stretch", hide_index=True)
        st.caption("Defaults live in src/rbac.py; an organisation can override them with instance/permissions.json "
                   "(changing that file is a server-side configuration task).")
    ev = [e for e in audit.load() if e["action"] in ("user_created", "user_updated", "role_changed", "user_deactivated",
                                                     "user_activated", "password_reset", "login_failed")]
    if ev:
        st.markdown("##### Account activity")
        st.dataframe(pd.DataFrame(ev)[["timestamp_utc", "username", "user_role", "action_label", "resource", "details"]].iloc[::-1],
                     width="stretch", hide_index=True)
