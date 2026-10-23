"""CorroSight by CorroGuard AI - Streamlit entry point.

Run:  streamlit run app.py      (create accounts first: python -m src.auth demo  or  python -m src.auth add ...)

Access flow: an unauthenticated session sees only the sign-in page (navigation hidden). After sign-in the account
is re-validated on every rerun (auth_ui.session_user); pages are filtered by role (src/rbac.py) and every page is
re-checked inside its wrapper, so a stale link or URL cannot open a page the role may not see.

Builds the grouped, vertical page navigation (st.navigation) and the sidebar data controls, applies the theme,
and runs the selected page. Pages live in ui_core.py (original four) and views.py (extended features); the
analysis itself lives in src/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import auth_ui as AU  # noqa: E402
import ui_core as U  # noqa: E402
import views as V  # noqa: E402
from src import APP_NAME, __version__, rbac, theme  # noqa: E402
from src.schema import LIMITATIONS  # noqa: E402

st.set_page_config(page_title="CorroSight | CorroGuard AI", page_icon=str(ROOT / "assets" / "corrosight_mark.svg"),
                   layout="wide", initial_sidebar_state="expanded")

# white workspace by default (config.toml); custom CSS and charts follow the active Streamlit theme
try:
    _mode = st.context.theme.type
except Exception:  # older Streamlit or bare test runs
    _mode = None
theme.set_mode(_mode or "light")
st.markdown(theme.css(), unsafe_allow_html=True)

# ---------------------------------------------------------------- authentication gate
# Every known page URL is answered with the sign-in page while signed out; after sign-in the same URL opens the page
# only if the role may see it (otherwise Home).
URL_KEYS = {"home": "home", "account": "account", "overview": "overview", "health-map": "health",
            "defect-history": "history", "event-timeline": "timeline", "identity-conflicts": "identity",
            "measurement-anomalies": "anomalies", "pattern-explorer": "patterns", "forecast-priorities": "forecast",
            "what-if": "whatif", "model-arena": "arena", "contradictions": "contradictions",
            "strategy-simulator": "strategy", "review-workbench": "workbench", "evidence-gaps": "gaps",
            "evidence-planning": "planning", "data-trust": "trust", "assistant": "assistant", "snapshots": "snapshots",
            "passport": "passport", "users": "users"}


def _signin_alias(url: str):
    def run():
        st.session_state["_nav_default"] = URL_KEYS[url]      # remembered through sign-in; access re-checked after
        AU.login_page()
    run.__name__ = f"signin_{url.replace('-', '_')}"
    return st.Page(run, title="Sign in", url_path=url)


user = AU.session_user()
if user is None:
    st.navigation([st.Page(AU.login_page, title="Sign in", url_path="login", default=True)] +
                  [_signin_alias(u) for u in URL_KEYS], position="hidden").run()
    st.stop()
if user.get("must_change_password"):
    st.navigation([st.Page(AU.forced_password_page, title="Set a new password", url_path="change-password", default=True)],
                  position="hidden").run()
    st.stop()

st.logo(str(ROOT / "assets" / "corrosight_logo.svg"), size="large", icon_image=str(ROOT / "assets" / "corrosight_mark.svg"))


def _page(fn, key: str, needs_data: bool = True):
    """Wrap a page: re-check access for the current user, show the landing screen until data is loaded, then the page."""
    def run():
        u = U.current_user()
        if not rbac.can_view(u, key):
            U.audit_log().record(u, "access_denied", f"page:{key}")
            st.error("You do not have access to this page with your current role. Contact your administrator if you "
                     "believe you need it.")
            return
        res = U.get_result()
        if not needs_data:
            fn(res)
            return
        if res is None:
            U.landing()
            return
        fn(res)
        with st.expander("Limitations of this prototype"):
            for lim in LIMITATIONS:
                st.markdown(f"- {lim}")
            st.caption(f"{APP_NAME} v{__version__}")
    run.__name__ = fn.__name__
    return run


# key, title, icon, function, url path
SECTIONS = {
    "Workspace": [
        ("home", "Home", ":material/home:", V.page_home, "home"),
        ("account", "My account", ":material/account_circle:", AU.page_account, "account"),
    ],
    "Overview": [
        ("overview", "Pipeline Overview", ":material/space_dashboard:", U.page_overview, "overview"),
        ("health", "Pipeline Health Map", ":material/grid_view:", V.page_health_map, "health-map"),
    ],
    "Inspection intelligence": [
        ("history", "Defect History", ":material/timeline:", U.page_history, "defect-history"),
        ("timeline", "Corrosion Event Timeline", ":material/event_note:", V.page_timeline, "event-timeline"),
        ("identity", "Defect Identity Conflicts", ":material/compare_arrows:", V.page_identity, "identity-conflicts"),
        ("anomalies", "Measurement Anomalies", ":material/troubleshoot:", V.page_anomalies, "measurement-anomalies"),
        ("patterns", "Corrosion Pattern Explorer", ":material/scatter_plot:", V.page_patterns, "pattern-explorer"),
    ],
    "Prediction & validation": [
        ("forecast", "Forecast & Priorities", ":material/query_stats:", U.page_forecast, "forecast-priorities"),
        ("whatif", "What-If Analysis", ":material/tune:", V.page_whatif, "what-if"),
        ("arena", "Model Challenge Arena", ":material/leaderboard:", V.page_arena, "model-arena"),
        ("contradictions", "Contradiction Finder", ":material/rule:", V.page_contradictions, "contradictions"),
    ],
    "Planning & review": [
        ("strategy", "Inspection Strategy Simulator", ":material/route:", V.page_strategy, "strategy-simulator"),
        ("workbench", "Engineering Review Workbench", ":material/engineering:", V.page_workbench, "review-workbench"),
        ("gaps", "Evidence Gap Finder", ":material/find_in_page:", V.page_gaps, "evidence-gaps"),
        ("planning", "Evidence & Planning", ":material/calculate:", U.page_evidence, "evidence-planning"),
    ],
    "Trust & evidence": [
        ("trust", "Data Trust Scorecard", ":material/verified_user:", V.page_trust, "data-trust"),
        ("assistant", "Evidence-Grounded Assistant", ":material/forum:", V.page_assistant, "assistant"),
        ("snapshots", "Reproducible Analysis Snapshots", ":material/history:", V.page_snapshots, "snapshots"),
        ("passport", "Evidence Passport & Audit Trail", ":material/description:", V.page_passport_audit, "passport"),
    ],
    "Administration": [
        ("users", "User management", ":material/manage_accounts:", AU.page_users, "users"),
    ],
}
NO_DATA_PAGES = {"home", "account", "users"}

# `_nav_default` lets tests (and deep links) choose the landing page; the user's choice otherwise persists.
# Only pages the role may see are registered, so other URLs fall back to Home.
default_key = st.session_state.get("_nav_default", "home")
if not rbac.can_view(user, default_key):
    default_key = "home"
pages = {}
U.NAV.clear()
for section, items in SECTIONS.items():
    visible = [it for it in items if rbac.can_view(user, it[0])]
    if not visible:
        continue
    pages[section] = []
    for key, title, icon, fn, url in visible:
        p = st.Page(_page(fn, key, key not in NO_DATA_PAGES), title=title, icon=icon, url_path=url, default=(key == default_key))
        U.NAV[key] = p
        pages[section].append(p)

nav = st.navigation(pages, position="sidebar", expanded=True)
AU.sidebar_user_card(user)
U.sidebar_controls()
nav.run()
