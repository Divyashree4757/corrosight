"""Central visual theme for CorroSight.

Two palettes share one layout:
  * "light" - white workspace with a navy sidebar and teal accents (default, set in .streamlit/config.toml).
  * "dark"  - dark cinematic industrial palette (kept for reference / optional use).
Streamlit picks the palette (Settings menu > Theme, or the OS preference); `set_mode()` is called on every run with
`st.context.theme.type`, so the custom CSS and Plotly charts follow the native widgets. `.streamlit/config.toml`
mirrors these tokens for native widgets. Status colours keep their meaning in both palettes.
"""

from __future__ import annotations

PALETTES = {
    "dark": dict(
        MODE="dark", NAVY_900="#060F18", NAVY_800="#0A1622", NAVY_700="#102532",
        BG="#08131F", SURFACE="#0C1925", SURFACE_2="#102532", PANEL="#142C38", BORDER="#28414D",
        TEAL="#28B8AC", TEAL_DARK="#17666A", TEAL_LIGHT="#45D6C5", TEAL_TINT="rgba(69,214,197,0.12)",
        TEXT="#EAF1F4", TEXT_2="#A8BBC5", MUTED="#7D929D", ON_NAVY="#EAF1F4", ON_NAVY_2="#A8BBC5",
        CORAL="#E0736A", AMBER="#E3A64A", VIOLET="#9C8FD6", BLUE="#6FA8DC", SLATE="#6E8291",
        WITHIN_NOISE="#3F5866", GRID="rgba(125,146,157,0.16)", PLOT_TEMPLATE="plotly_dark",
        BANNER_BG="rgba(227,166,74,0.08)", BANNER_BORDER="rgba(227,166,74,0.35)", BANNER_TEXT="#EBD3A8",
        SHADOW="none", FOCUS="#45D6C5",
        TAGS=dict(obs=("rgba(111,168,220,0.14)", "#A9CDF0"), calc=("rgba(40,184,172,0.14)", "#5FE0D2"),
                  pred=("rgba(227,166,74,0.14)", "#F2C77F"), unc=("rgba(156,143,214,0.16)", "#C9BFF3"),
                  miss=("rgba(224,115,106,0.14)", "#F3ABA4")),
    ),
    "light": dict(
        MODE="light", NAVY_900="#0B1620", NAVY_800="#0F1F2C", NAVY_700="#16293A",
        BG="#FFFFFF", SURFACE="#FFFFFF", SURFACE_2="#F5F8FA", PANEL="#FFFFFF", BORDER="#DCE3E8",
        TEAL="#1F9E92", TEAL_DARK="#167A72", TEAL_LIGHT="#5FC8BE", TEAL_TINT="rgba(31,158,146,0.10)",
        TEXT="#14222E", TEXT_2="#4A5B68", MUTED="#6F808C", ON_NAVY="#E6EEF2", ON_NAVY_2="#9DB0BC",
        CORAL="#D64F45", AMBER="#C9861F", VIOLET="#7B6FC4", BLUE="#3E7CB1", SLATE="#8A99A6",
        WITHIN_NOISE="#B7C4CD", GRID="rgba(20,34,46,0.08)", PLOT_TEMPLATE="plotly_white",
        BANNER_BG="#FFF8EC", BANNER_BORDER="#F0D9B0", BANNER_TEXT="#7A4E0E",
        SHADOW="0 1px 2px rgba(20,34,46,0.05)", FOCUS="#167A72",
        TAGS=dict(obs=("#E3EEF8", "#2C5F8A"), calc=("#E0F4F1", "#167A72"), pred=("#FBF0DC", "#8A5A12"),
                  unc=("#ECEAF8", "#574BA0"), miss=("#FBE5E3", "#A23A32")),
    ),
}

# Active palette values (filled by set_mode; declared here so tools and readers can see the names).
MODE = NAVY_900 = NAVY_800 = NAVY_700 = BG = SURFACE = SURFACE_2 = PANEL = BORDER = ""
TEAL = TEAL_DARK = TEAL_LIGHT = TEAL_TINT = TEXT = TEXT_2 = MUTED = ON_NAVY = ON_NAVY_2 = ""
CORAL = AMBER = VIOLET = BLUE = SLATE = WITHIN_NOISE = GRID = PLOT_TEMPLATE = ""
CAT_COLOURS: dict = {}
MATCH_COLOURS: dict = {}
CHANGE_COLOURS: dict = {}
FONT_FAMILY = "Inter, 'Segoe UI', system-ui, -apple-system, sans-serif"


def set_mode(mode: str | None) -> str:
    """Activate a palette ('light' default). Mutates the colour dicts in place so importers see the change."""
    mode = mode if mode in PALETTES else "light"
    globals().update(PALETTES[mode])
    CAT_COLOURS.clear()
    CAT_COLOURS.update({"Review first": CORAL, "Verify match / data": AMBER, "Additional data needed": VIOLET,
                        "Monitor": TEAL, "Routine review": SLATE})
    MATCH_COLOURS.clear()
    MATCH_COLOURS.update({"Likely match": TEAL, "Ambiguous match": AMBER, "Not found in later run": CORAL,
                          "New in later run": BLUE, "Excluded from matching": SLATE})
    CHANGE_COLOURS.clear()
    CHANGE_COLOURS.update({"INCREASE_BEYOND_NOISE": TEAL, "WITHIN_NOISE": WITHIN_NOISE,
                           "DECREASE_BEYOND_NOISE": VIOLET, "UNCERTAINTY_UNKNOWN": AMBER})
    return mode


set_mode("light")

# ---------------------------------------------------------------- brand mark (teal ribbon "S")
LOGO_MARK_SVG = """<svg viewBox="0 0 40 56" xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">
<defs><linearGradient id="csg1" x1="0.2" y1="0" x2="0.8" y2="1"><stop offset="0" stop-color="#8FE0D6"/><stop offset="1" stop-color="#2AA79B"/></linearGradient>
<linearGradient id="csg2" x1="0.8" y1="0" x2="0.2" y2="1"><stop offset="0" stop-color="#3FB5A9"/><stop offset="1" stop-color="#14706A"/></linearGradient></defs>
<path d="M33 1 C20 6 9 13 8 22 C7.5 27 11 30.5 16 33 C12 29 13 24.5 18 20.5 C22.5 17 28 12 33 1 Z" fill="url(#csg1)"/>
<path d="M16 33 C22 36.5 27 39 26.5 44 C26 49 19 52.5 11 55 C23 54 32 48.5 32.5 41 C33 34 26 30 21 27 C17.5 25 16.5 23 18 20.5 C13 24.5 12 29 16 33 Z" fill="url(#csg2)"/>
</svg>"""

LOGO_FULL_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 250 64" width="250" height="64">
<defs><linearGradient id="g1" x1="0.2" y1="0" x2="0.8" y2="1"><stop offset="0" stop-color="#8FE0D6"/><stop offset="1" stop-color="#2AA79B"/></linearGradient>
<linearGradient id="g2" x1="0.8" y1="0" x2="0.2" y2="1"><stop offset="0" stop-color="#3FB5A9"/><stop offset="1" stop-color="#14706A"/></linearGradient></defs>
<g transform="translate(2,4)"><path d="M33 1 C20 6 9 13 8 22 C7.5 27 11 30.5 16 33 C12 29 13 24.5 18 20.5 C22.5 17 28 12 33 1 Z" fill="url(#g1)"/>
<path d="M16 33 C22 36.5 27 39 26.5 44 C26 49 19 52.5 11 55 C23 54 32 48.5 32.5 41 C33 34 26 30 21 27 C17.5 25 16.5 23 18 20.5 C13 24.5 12 29 16 33 Z" fill="url(#g2)"/></g>
<text x="46" y="34" font-family="Inter, Segoe UI, Helvetica, Arial, sans-serif" font-size="27" font-weight="600" fill="#EAF1F4">CorroSight</text>
<text x="47" y="53" font-family="Inter, Segoe UI, Helvetica, Arial, sans-serif" font-size="10.5" fill="#8FA9B6" letter-spacing="0.6">PIPELINE INTEGRITY EVIDENCE</text>
</svg>"""


def logo_html(size: int = 30, text_size: str = "1.45rem", text_colour: str | None = None) -> str:
    mark = LOGO_MARK_SVG.format(w=int(size * 40 / 56), h=size)
    col = text_colour or ON_NAVY
    return f"<div class='cs-logo'>{mark}<span style='font-size:{text_size};color:{col}'>CorroSight</span></div>"


def plotly_layout(height: int) -> dict:
    return dict(
        template=PLOT_TEMPLATE, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=SURFACE,
        height=height, margin=dict(l=10, r=30, t=46, b=70),
        font=dict(color=TEXT_2, size=12, family=FONT_FAMILY),
        title_font=dict(size=14, color=TEXT), title_x=0, title_y=0.98, title_yanchor="top",
        legend=dict(orientation="h", yanchor="top", y=-0.22, x=0, bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT_2)),
        hoverlabel=dict(bgcolor=NAVY_800, bordercolor=TEAL, font=dict(color=ON_NAVY, family=FONT_FAMILY)),
    )


def css() -> str:
    P = PALETTES[MODE]
    T = P["TAGS"]
    return f"""
<style>
:root {{ --cs-teal: {P['TEAL']}; --cs-teal-dark: {P['TEAL_DARK']}; --cs-teal-light: {P['TEAL_LIGHT']}; --cs-tint: {P['TEAL_TINT']};
  --cs-navy: {P['NAVY_900']}; --cs-navy-2: {P['NAVY_800']}; --cs-bg: {P['BG']}; --cs-surface: {P['SURFACE']};
  --cs-surface-2: {P['SURFACE_2']}; --cs-border: {P['BORDER']}; --cs-text: {P['TEXT']}; --cs-text-2: {P['TEXT_2']};
  --cs-muted: {P['MUTED']}; --cs-coral: {P['CORAL']}; --cs-amber: {P['AMBER']}; --cs-focus: {P['FOCUS']}; }}
html, body, [data-testid="stAppViewContainer"] {{ font-family: {FONT_FAMILY}; }}
[data-testid="stAppViewContainer"] {{ background: var(--cs-bg); }}
[data-testid="stHeader"] {{ background: var(--cs-navy-2); border-bottom: 1px solid {P['NAVY_700']}; }}
[data-testid="stHeader"] * {{ color: {P['ON_NAVY']}; }}
.block-container {{ padding-top: 3.6rem; max-width: 1500px; }}
h1, h2, h3, h4 {{ color: var(--cs-text); letter-spacing: -0.015em; font-weight: 650; }}
h2 {{ font-size: 1.65rem; }}
*:focus-visible {{ outline: 2px solid var(--cs-focus) !important; outline-offset: 2px; }}

/* ---------- sidebar: logo + grouped vertical navigation (st.navigation) ---------- */
[data-testid="stSidebar"] {{ background: var(--cs-navy); border-right: 1px solid {P['NAVY_700']}; }}
[data-testid="stSidebar"][data-collapsed="false"], [data-testid="stSidebar"][aria-expanded="true"] {{ width: 352px !important; min-width: 352px !important; }}
[data-testid="stSidebar"][data-collapsed="true"], [data-testid="stSidebar"][aria-expanded="false"] {{ width: 0 !important; min-width: 0 !important; overflow: hidden; }}
[data-testid="stSidebarHeader"] {{ padding-bottom: 0.4rem; }}
[data-testid="stSidebarLogo"], [data-testid="stHeaderLogo"] {{ height: 2.9rem !important; max-width: 100%; }}
[data-testid="stSidebarNav"] {{ padding-top: 0.2rem; }}
[data-testid="stNavSectionHeader"] {{ color: {P['ON_NAVY_2']} !important; font-size: 0.68rem !important; font-weight: 700 !important;
  letter-spacing: 0.12em; text-transform: uppercase; margin: 0.9rem 0 0.15rem 0.2rem !important; opacity: 0.85; }}
[data-testid="stSidebarNavLink"] {{ display: flex; align-items: center; gap: 0.55rem; padding: 0.3rem 0.65rem !important;
  margin: 1px 0 !important; border-left: 3px solid transparent; border-radius: 0 6px 6px 0 !important; min-height: 2rem; }}
[data-testid="stSidebarNavLink"] span {{ color: {P['ON_NAVY_2']} !important; font-size: 0.9rem; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }}
[data-testid="stSidebarNavLink"]:hover {{ background: rgba(69,214,197,0.07) !important; }}
[data-testid="stSidebarNavLink"][aria-current="page"] {{ border-left-color: {P['TEAL_LIGHT']};
  background: linear-gradient(90deg, rgba(69,214,197,0.16), rgba(69,214,197,0.02)) !important; }}
[data-testid="stSidebarNavLink"][aria-current="page"] span {{ color: {P['TEAL_LIGHT']} !important; font-weight: 600; }}
[data-testid="stSidebarNavSeparator"] {{ border-color: {P['NAVY_700']}; }}
.cs-logo {{ display: flex; align-items: center; gap: 0.5rem; font-weight: 600; letter-spacing: -0.01em; }}
.cs-side-h {{ color: {P['ON_NAVY_2']}; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase;
  margin: 0.4rem 0 0.2rem 0; }}
.cs-side-foot {{ display: flex; gap: 0.6rem; align-items: center; color: {P['ON_NAVY_2']}; font-size: 0.76rem; }}
.cs-avatar {{ width: 32px; height: 32px; border-radius: 50%; background: linear-gradient(135deg, {P['TEAL_LIGHT']}, {P['TEAL_DARK']});
  display: flex; align-items: center; justify-content: center; color: white; font-weight: 700; font-size: 0.8rem; flex: none; }}

/* ---------- top bar ---------- */
.cs-topbar {{ display: flex; align-items: center; justify-content: space-between; background: var(--cs-navy-2);
  border: 1px solid {P['NAVY_700']}; border-radius: 10px; padding: 0.5rem 0.9rem; margin: -0.6rem 0 1rem 0; gap: 0.8rem; flex-wrap: wrap; }}
.cs-search {{ display: flex; align-items: center; gap: 0.5rem; background: {P['NAVY_700']}; border: 1px solid {P['BORDER'] if P['MODE'] == 'dark' else '#22394C'};
  color: {P['ON_NAVY_2']}; border-radius: 6px; padding: 0.28rem 0.75rem; font-size: 0.84rem; }}
.cs-search b {{ color: {P['ON_NAVY']}; font-weight: 600; }}
.cs-chip {{ font-size: 0.7rem; font-weight: 700; letter-spacing: 0.04em; padding: 3px 9px; border-radius: 12px; white-space: nowrap; }}
.cs-chip.syn {{ background: rgba(227,166,74,0.16); color: #F2C57C; border: 1px solid rgba(227,166,74,0.45); }}
.cs-chip.user {{ background: rgba(23,102,106,0.10); color: {P['TEAL']}; border: 1px solid rgba(23,102,106,0.35); }}
.cs-usercard {{ display: flex; gap: 0.65rem; align-items: center; padding: 0.55rem 0.6rem; margin: 0.2rem 0 0.4rem;
  border: 1px solid rgba(230,238,242,0.14); border-radius: 10px; background: rgba(255,255,255,0.04); }}
.cs-usercard .n {{ color: #E6EEF2; font-weight: 700; font-size: 0.88rem; line-height: 1.2; }}
.cs-usercard .r {{ color: {P['ON_NAVY_2']}; font-size: 0.74rem; line-height: 1.25; }}
.cs-chip.real {{ background: rgba(95,200,190,0.14); color: {P['TEAL_LIGHT']}; border: 1px solid rgba(95,200,190,0.45); }}
.cs-desc {{ color: var(--cs-text-2); font-size: 0.92rem; margin: -0.4rem 0 0.9rem 0; max-width: 1100px; }}

/* ---------- landing splash ---------- */
.cs-splash {{ background: radial-gradient(900px 300px at 50% 0%, #15303F 0%, {P['NAVY_900']} 70%); border: 1px solid {P['NAVY_700']};
  border-radius: 14px; padding: 2.4rem 1.5rem 2rem 1.5rem; margin-bottom: 1.1rem; display: flex; flex-direction: column; align-items: center; }}
.cs-splash-sub {{ color: {P['ON_NAVY_2']}; margin-top: 0.8rem; font-size: 1rem; text-align: center; }}

/* ---------- workspace panels ---------- */
.cs-banner {{ border: 1px solid {P['BANNER_BORDER']}; border-left: 4px solid var(--cs-amber); background: {P['BANNER_BG']};
  padding: 0.5rem 0.9rem; border-radius: 6px; color: {P['BANNER_TEXT']}; font-size: 0.85rem; margin-bottom: 0.8rem; }}
.cs-kpi {{ background: var(--cs-surface); border: 1px solid var(--cs-border); border-radius: 10px; padding: 0.7rem 0.95rem;
  height: 100%; box-shadow: {P['SHADOW']}; }}
.cs-kpi.hi {{ border-top: 3px solid var(--cs-teal); }}
.cs-kpi .v {{ font-size: 1.5rem; font-weight: 700; color: var(--cs-text); line-height: 1.15; font-variant-numeric: tabular-nums; }}
.cs-kpi .l {{ font-size: 0.68rem; color: var(--cs-muted); text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600; }}
.cs-kpi .s {{ font-size: 0.74rem; color: var(--cs-text-2); }}
.cs-flow {{ display: flex; gap: 6px; flex-wrap: wrap; margin: 0.3rem 0 1rem 0; }}
.cs-step {{ flex: 1 1 120px; background: var(--cs-surface); border: 1px solid var(--cs-border); border-radius: 8px;
  padding: 0.45rem 0.65rem; border-top: 3px solid var(--cs-border); }}
.cs-step .n {{ color: var(--cs-muted); font-size: 0.66rem; font-weight: 700; letter-spacing: 0.08em; }}
.cs-step .t {{ color: var(--cs-text); font-size: 0.82rem; font-weight: 600; }}
.cs-step .d {{ color: var(--cs-text-2); font-size: 0.72rem; }}
.cs-step.done {{ border-top-color: var(--cs-teal); }}
.cs-step.done .n {{ color: {P['TEAL_LIGHT'] if P['MODE'] == 'dark' else P['TEAL_DARK']}; }}
.tag {{ display: inline-block; font-size: 0.64rem; font-weight: 700; letter-spacing: 0.08em; padding: 2px 7px;
  border-radius: 3px; margin-right: 6px; vertical-align: middle; }}
.t-obs {{ background: {T['obs'][0]}; color: {T['obs'][1]}; }} .t-calc {{ background: {T['calc'][0]}; color: {T['calc'][1]}; }}
.t-pred {{ background: {T['pred'][0]}; color: {T['pred'][1]}; }} .t-unc {{ background: {T['unc'][0]}; color: {T['unc'][1]}; }}
.t-miss {{ background: {T['miss'][0]}; color: {T['miss'][1]}; }}
.cs-card {{ background: var(--cs-surface); border: 1px solid var(--cs-border); border-radius: 10px; padding: 0.8rem 1rem;
  margin-bottom: 0.6rem; box-shadow: {P['SHADOW']}; }}
.cs-card.accent {{ border-left: 3px solid var(--cs-teal); }}
.cs-card h4 {{ margin: 0 0 0.35rem 0; font-size: 0.93rem; color: var(--cs-text); }}
.cs-card p, .cs-card li {{ font-size: 0.85rem; color: var(--cs-text-2); margin-bottom: 0.2rem; }}
.cs-card b {{ color: var(--cs-text); }}
.cat {{ display: inline-block; padding: 2px 10px; border-radius: 4px; font-size: 0.74rem; font-weight: 700; color: #FFFFFF; white-space: nowrap; }}
.muted {{ color: var(--cs-muted); font-size: 0.8rem; }}
.cs-ev {{ border-left: 3px solid var(--cs-border); padding: 0.35rem 0 0.45rem 0.85rem; margin-left: 0.4rem; position: relative; }}
.cs-ev::before {{ content: ""; position: absolute; left: -7px; top: 0.6rem; width: 11px; height: 11px; border-radius: 50%;
  background: var(--cs-surface); border: 2px solid var(--cs-teal); }}
.cs-ev.src::before {{ background: var(--cs-teal); }} .cs-ev.log::before {{ border-color: var(--cs-amber); }}
.cs-ev .w {{ color: var(--cs-muted); font-size: 0.75rem; }} .cs-ev .e {{ color: var(--cs-text); font-weight: 600; font-size: 0.9rem; }}
.cs-ev .v {{ color: var(--cs-text-2); font-size: 0.84rem; }}
.cs-vs {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }}
.cs-vs > div {{ background: var(--cs-surface-2); border: 1px solid var(--cs-border); border-radius: 8px; padding: 0.5rem 0.7rem;
  font-size: 0.84rem; color: var(--cs-text-2); }}
.cs-vs b {{ color: var(--cs-text); }}
.cs-chat {{ background: var(--cs-surface); border: 1px solid var(--cs-border); border-radius: 10px; padding: 0.7rem 0.9rem; margin-bottom: 0.5rem; }}

/* ---------- Why-Inspect-First row list ---------- */
.cs-prow {{ display: grid; grid-template-columns: minmax(240px, 1.1fr) 130px minmax(300px, 1.6fr); gap: 0.9rem;
  align-items: stretch; background: var(--cs-surface); border: 1px solid var(--cs-border); border-radius: 10px;
  padding: 0.75rem 0.9rem; margin-bottom: 0.5rem; }}
.cs-prow.sel {{ border-color: var(--cs-teal); box-shadow: 0 0 0 2px var(--cs-tint); }}
.cs-prow .t {{ font-weight: 650; color: var(--cs-text); font-size: 0.96rem; }}
.cs-prow .m {{ color: var(--cs-muted); font-size: 0.78rem; margin-top: 2px; }}
.cs-prow .pill {{ display: inline-block; font-size: 0.66rem; font-weight: 700; padding: 1px 6px; border-radius: 3px;
  background: var(--cs-tint); color: {P['TEAL_LIGHT'] if P['MODE'] == 'dark' else P['TEAL_DARK']}; margin-left: 6px; vertical-align: middle; }}
.cs-prow .why {{ border-left: 3px solid var(--cs-teal); background: var(--cs-surface-2); border-radius: 0 6px 6px 0; padding: 0.45rem 0.7rem; }}
.cs-prow .why h5 {{ margin: 0; font-size: 0.9rem; color: var(--cs-text); }}
.cs-prow .why p {{ margin: 0.15rem 0 0 0; font-size: 0.8rem; color: var(--cs-text-2); }}
.cs-prow .why .ne {{ float: right; font-size: 0.64rem; font-weight: 700; color: {P['TEAL_LIGHT'] if P['MODE'] == 'dark' else P['TEAL_DARK']};
  background: var(--cs-tint); padding: 1px 6px; border-radius: 3px; }}
@media (max-width: 1000px) {{ .cs-prow, .cs-vs {{ grid-template-columns: 1fr; }} }}

/* ---------- native widgets ---------- */
.stTabs [data-baseweb="tab-list"] {{ border-bottom: 1px solid var(--cs-border); gap: 0.6rem; flex-wrap: wrap; }}
.stTabs [data-baseweb="tab"] p {{ color: var(--cs-text-2); font-weight: 500; }}
.stTabs [aria-selected="true"] p {{ color: var(--cs-text) !important; font-weight: 650; }}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: var(--cs-teal) !important; height: 3px; }}
[data-testid="stPlotlyChart"] {{ background: var(--cs-surface); border: 1px solid var(--cs-border); border-radius: 10px; padding: 0.35rem 0.5rem 0 0.5rem; }}
[data-testid="stDataFrame"] {{ border: 1px solid var(--cs-border); border-radius: 8px; }}
[data-testid="stMain"] [data-testid="stForm"], [data-testid="stMain"] [data-testid="stExpander"] details {{
  background: var(--cs-surface); border: 1px solid var(--cs-border) !important; border-radius: 10px; }}
</style>
"""


def login_css() -> str:
    """Dark brand styling for the sign-in screen only (the workspace keeps its own theme)."""
    return """
<style>
[data-testid="stAppViewContainer"] { background: radial-gradient(1100px 520px at 18% 10%, #12313B 0%, #08131F 62%) !important; }
[data-testid="stHeader"] { background: transparent !important; border: none !important; }
[data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] { display: none !important; }
[data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3, [data-testid="stMain"] p,
[data-testid="stMain"] label, [data-testid="stMain"] span, [data-testid="stMain"] li { color: #EAF1F4; }
.block-container { max-width: 1120px; padding-top: 4.5rem; }
.cs-login-brand { border: 1px solid #28414D; border-radius: 14px; padding: 2rem 2rem 0 2rem;
  background: linear-gradient(160deg, #0C1925 0%, #102532 70%, rgba(23,102,106,0.45) 100%); position: relative; overflow: hidden; }
.cs-login-brand .tag { color: #45D6C5; font-size: 0.72rem; letter-spacing: 0.16em; font-weight: 700; text-transform: uppercase;
  margin-top: 0.5rem; display: block; }
.cs-login-brand h3 { color: #EAF1F4; font-weight: 600; font-size: 1.35rem; margin: 1.6rem 0 0.6rem 0; line-height: 1.35; }
.cs-login-brand p, .cs-login-brand li { color: #A8BBC5 !important; font-size: 0.92rem; }
.cs-login-brand ul { padding-left: 1.1rem; margin-top: 0.6rem; }
.cs-login-brand svg.pipe { display: block; margin: 1.4rem -2rem 0 -2rem; width: calc(100% + 4rem); height: 110px; opacity: 0.9; }
.cs-login-card { padding: 0.4rem 0 0.8rem 0; }
.cs-login-card h2 { color: #EAF1F4 !important; font-size: 1.7rem; margin: 0 0 0.2rem 0; }
.cs-login-card .sub { color: #A8BBC5; font-size: 0.93rem; margin-bottom: 0.4rem; }
[data-testid="stMain"] [data-testid="stForm"] { background: #0C1925 !important; border: 1px solid #28414D !important;
  border-radius: 14px !important; padding: 1.6rem 1.7rem 1.4rem 1.7rem !important; box-shadow: 0 18px 50px rgba(0,0,0,0.35); }
[data-testid="stTextInputRootElement"], [data-testid="stTextInputRootElement"] > div, [data-baseweb="input"] {
  background: #102532 !important; border-color: #28414D !important; }
[data-testid="stTextInputRootElement"] input { color: #EAF1F4 !important; -webkit-text-fill-color: #EAF1F4 !important; background: #102532 !important; }
[data-testid="stTextInputRootElement"] input::placeholder { color: #7D929D !important; -webkit-text-fill-color: #7D929D !important; }
[data-testid="stTextInputRootElement"]:focus-within { border-color: #45D6C5 !important; box-shadow: 0 0 0 1px rgba(69,214,197,0.35); }
[data-testid="stTextInputRootElement"] button { background: transparent !important; color: #A8BBC5 !important; }
[data-testid="stFormSubmitButton"] button { width: 100%; background: linear-gradient(180deg, #1D7C7F, #17666A) !important;
  border: 1px solid rgba(69,214,197,0.5) !important; color: #F2FBFA !important; font-weight: 600; padding: 0.55rem 0; }
[data-testid="stFormSubmitButton"] button p { color: #F2FBFA !important; }
[data-testid="stAlert"] p { color: inherit; }
.cs-login-foot { color: #7D929D; font-size: 0.78rem; text-align: center; margin-top: 1.4rem; }
.cs-login-foot span { color: #7D929D !important; }
[data-testid="stCaptionContainer"] p { color: #7D929D !important; }
code { background: #142C38 !important; color: #45D6C5 !important; }
@media (max-width: 900px) { .block-container { padding-top: 2rem; } .cs-login-brand svg.pipe { display: none; }
  .cs-login-brand { padding-bottom: 1.4rem; } }
</style>
"""


PIPE_SVG = """<svg class="pipe" viewBox="0 0 600 130" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
<defs><linearGradient id="pg" x1="0" x2="1"><stop offset="0" stop-color="#17666A" stop-opacity="0.2"/>
<stop offset="0.5" stop-color="#28B8AC" stop-opacity="0.75"/><stop offset="1" stop-color="#17666A" stop-opacity="0.2"/></linearGradient></defs>
<rect x="0" y="62" width="600" height="22" rx="3" fill="#142C38" stroke="#28414D"/>
<rect x="0" y="70" width="600" height="2" fill="url(#pg)"/>
<g stroke="#28414D" stroke-width="2">
<line x1="75" y1="58" x2="75" y2="88"/><line x1="195" y1="58" x2="195" y2="88"/><line x1="315" y1="58" x2="315" y2="88"/>
<line x1="435" y1="58" x2="435" y2="88"/><line x1="555" y1="58" x2="555" y2="88"/></g>
<g fill="#45D6C5"><circle cx="128" cy="73" r="3.2"/><circle cx="262" cy="76" r="2.4"/><circle cx="389" cy="72" r="4"/>
<circle cx="508" cy="75" r="2.6"/></g>
<g fill="none" stroke="#45D6C5" stroke-opacity="0.35"><circle cx="389" cy="72" r="10"/><circle cx="128" cy="73" r="8"/></g>
<polyline points="0,40 90,36 170,38 260,30 340,33 420,24 500,27 600,18" fill="none" stroke="#28B8AC" stroke-opacity="0.45" stroke-width="1.5"/>
</svg>"""
