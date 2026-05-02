"""
app.py — GeoSentinel Terminal
Bloomberg-style live trading terminal.
Run: streamlit run app.py
"""

import streamlit as st
from config import DEMO_MODE
from src.utils import render_error_card

st.set_page_config(
    page_title="GeoSentinel Terminal",
    page_icon="⬛",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Password Gate ─────────────────────────────────────────────────────────────
# Active only when APP_PASSWORD is set in .streamlit/secrets.toml (or the
# Streamlit Cloud secrets dashboard). Skipped entirely in local dev when the
# key is absent — no friction on your own machine.
_app_pw = st.secrets.get("APP_PASSWORD", "")
if _app_pw and not st.session_state.get("_authenticated"):
    st.markdown("""
    <div style='max-width:360px;margin:120px auto 0 auto;
                background:#161b22;border:1px solid #30363d;border-radius:8px;
                padding:40px 36px;font-family:IBM Plex Mono,monospace;text-align:center'>
      <div style='font-size:22px;font-weight:700;color:#00FFB2;
                  letter-spacing:2px;margin-bottom:6px'>GEOSENTINEL</div>
      <div style='font-size:10px;color:#8b949e;letter-spacing:2px;
                  margin-bottom:32px'>REGIME-AWARE INTELLIGENCE</div>
    </div>
    """, unsafe_allow_html=True)
    _col = st.columns([1, 2, 1])[1]
    with _col:
        _entered = st.text_input("Access code", type="password",
                                 placeholder="enter access code",
                                 label_visibility="collapsed")
        if _entered == _app_pw:
            st.session_state["_authenticated"] = True
            st.rerun()
        elif _entered:
            st.error("Incorrect access code.")
    st.stop()

# ── Bloomberg Terminal CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

html, body, .stApp {
  background-color: #0d1117 !important;
  color: #c9d1d9 !important;
  font-family: 'IBM Plex Sans', sans-serif !important;
}
[data-testid="stSidebar"] {
  background-color: #010409 !important;
  border-right: 1px solid #21262d !important;
}
[data-testid="stSidebar"] * { color: #c9d1d9 !important; }

/* Top bar */
.t-bar { display:flex; gap:8px; padding:10px 0 10px 0;
         border-bottom:1px solid #21262d; margin-bottom:6px; flex-wrap:wrap; }
.t-card { background:#161b22; border:1px solid #30363d; border-radius:5px;
          padding:7px 14px; min-width:130px; font-family:'IBM Plex Mono',monospace; }
.t-card .lbl { font-size:9px; color:#8b949e; letter-spacing:1.2px;
               text-transform:uppercase; margin-bottom:3px; }
.t-card .val { font-size:15px; font-weight:600; color:#c9d1d9; }
.t-card .val.green  { color:#3fb950; }
.t-card .val.red    { color:#f85149; }
.t-card .val.teal   { color:#00FFB2; }
.t-card .val.yellow { color:#e3b341; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
  background:#010409 !important;
  border-bottom:1px solid #21262d !important;
  gap:0;
}
.stTabs [data-baseweb="tab"] {
  background:transparent !important;
  color:#8b949e !important;
  font-size:11px !important;
  font-weight:700 !important;
  letter-spacing:1.2px !important;
  text-transform:uppercase !important;
  padding:12px 24px !important;
  border-radius:0 !important;
  border-bottom:2px solid transparent !important;
}
.stTabs [aria-selected="true"] {
  color:#00FFB2 !important;
  border-bottom:2px solid #00FFB2 !important;
  background:#0d1117 !important;
}
.stTabs [data-baseweb="tab"]:hover { color:#c9d1d9 !important; background:#161b22 !important; }
.stTabs [data-baseweb="tab-panel"] { background:#0d1117 !important; padding-top:4px; }

/* Metrics */
[data-testid="stMetric"] {
  background:#161b22 !important; border:1px solid #30363d !important;
  border-radius:6px !important; padding:12px 16px !important;
}
[data-testid="stMetricLabel"] { color:#8b949e !important; font-size:11px !important; letter-spacing:0.5px; }
[data-testid="stMetricValue"] { color:#c9d1d9 !important; font-family:'IBM Plex Mono',monospace !important; }
[data-testid="stMetricDelta"] { font-family:'IBM Plex Mono',monospace !important; }

/* Dataframes */
[data-testid="stDataFrame"] { border:1px solid #30363d !important; border-radius:6px !important; }

/* Buttons */
.stButton > button {
  background:#238636 !important; color:#fff !important;
  border:1px solid #2ea043 !important; border-radius:6px !important;
  font-weight:700 !important; font-family:'IBM Plex Mono',monospace !important;
  letter-spacing:0.5px !important; padding:8px 20px !important;
}
.stButton > button:hover { background:#2ea043 !important; }
button[kind="primary"] { background:#238636 !important; }

/* Selectbox — trigger */
[data-testid="stSelectbox"] > div > div {
  background:#161b22 !important; border:1px solid #30363d !important; color:#c9d1d9 !important;
}
/* Selectbox — dropdown popover & options list */
[data-baseweb="popover"],
[data-baseweb="menu"],
[data-baseweb="select"],
ul[role="listbox"],
[role="listbox"],
[data-baseweb="list"],
[data-baseweb="option"] {
  background:#0d1117 !important;
  border:1px solid #30363d !important;
  color:#c9d1d9 !important;
}
li[role="option"],
[data-baseweb="option"]:hover,
[aria-selected="true"] {
  background:#161b22 !important;
  color:#c9d1d9 !important;
}
/* Segmented control */
[data-testid="stSegmentedControl"] button {
  background:#161b22 !important; border:1px solid #30363d !important; color:#8b949e !important;
}
[data-testid="stSegmentedControl"] button[aria-checked="true"] {
  background:#21262d !important; color:#00FFB2 !important; border-color:#00FFB2 !important;
}

/* Expander — full dark theme for all Streamlit 1.42+ layers */
[data-testid="stExpander"],
[data-testid="stExpander"] > details,
[data-testid="stExpander"] details,
[data-testid="stExpanderDetails"] {
  background:#161b22 !important;
  border:1px solid #30363d !important;
  border-radius:6px !important;
}
[data-testid="stExpander"] details > summary,
[data-testid="stExpander"] summary {
  background:#161b22 !important;
  color:#c9d1d9 !important;
  border-radius:6px !important;
}
[data-testid="stExpander"] summary:hover { background:#21262d !important; }
/* Slider — dark track, thumb, and fill for Streamlit 1.42+ BaseUI */
[data-testid="stSlider"] > div > div,
[data-testid="stSlider"] [data-baseweb="slider"],
[data-testid="stSlider"] [data-baseweb="slider"] > div {
  background:transparent !important;
}
[data-testid="stSlider"] [role="slider"] {
  background:#00FFB2 !important;
  border-color:#00FFB2 !important;
}
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] + div {
  background:#00FFB2 !important;
}

/* News cards */
.news-card {
  background:#161b22; border:1px solid #30363d; border-radius:6px;
  padding:12px 16px; margin-bottom:8px;
}
.news-card:hover { border-color:#58a6ff; cursor:pointer; }
.news-headline { font-size:13px; font-weight:500; color:#c9d1d9; margin:4px 0; line-height:1.4; }
.news-meta { font-size:11px; color:#8b949e; font-family:'IBM Plex Mono',monospace; margin-top:5px; }
.badge { display:inline-block; padding:2px 7px; border-radius:3px; font-size:9px;
         font-weight:700; font-family:'IBM Plex Mono',monospace; letter-spacing:0.5px; margin-right:6px; }
.badge-bear { background:#f8514918; color:#f85149; border:1px solid #f8514940; }
.badge-bull { background:#3fb95018; color:#3fb950; border:1px solid #3fb95040; }
.badge-neut { background:#e3b34118; color:#e3b341; border:1px solid #e3b34140; }
.tkr { display:inline-block; padding:1px 5px; background:#21262d; border:1px solid #30363d;
       border-radius:3px; font-size:10px; font-weight:700; color:#00FFB2;
       font-family:'IBM Plex Mono',monospace; margin-right:3px; }

/* Regime banner */
.regime-banner {
  padding:10px 16px; border-radius:6px; margin-bottom:16px;
  font-family:'IBM Plex Mono',monospace;
}

/* Hide Streamlit chrome */
#MainMenu { visibility:hidden; }
footer    { visibility:hidden; }
header    { visibility:hidden; }
[data-testid="stToolbar"] { display:none; }
/* Hide sidebar entirely — all key info lives in the top bar */
[data-testid="collapsedControl"] { display:none !important; }
section[data-testid="stSidebar"]  { display:none !important; }
</style>
""", unsafe_allow_html=True)


# ── Top bar data — lazy via session_state so network calls never block startup ─
def _bar_data():
    """
    Load regime + account data once per 5-minute window via session_state.
    Never called at module level — only inside the render path after Streamlit
    has fully initialized its HTTP server.
    """
    import time
    now = time.time()
    if (
        "bar_data_cache" not in st.session_state
        or now - st.session_state.get("bar_data_ts", 0) > 300
    ):
        try:
            from src.models.regime import get_current_regime
            from src.data.fetchers import fetch_alpaca_account
            st.session_state["bar_data_cache"] = (
                get_current_regime(demo_mode=True), fetch_alpaca_account()
            )
        except Exception:
            st.session_state["bar_data_cache"] = ({}, {})
        st.session_state["bar_data_ts"] = now
    return st.session_state["bar_data_cache"]

regime_info, acct = _bar_data()
# Share regime_info via session_state so all tabs read the same cached value
st.session_state["regime_info"] = regime_info
regime_label  = regime_info.get("label", "—")
regime_prob   = regime_info.get("prob", 0.0)
regime_source = regime_info.get("source", "live")
brent_vol     = regime_info.get("brent_vol", 0.0)
rc = "red" if regime_label == "Crisis" else "yellow" if regime_label == "Elevated" else "green"
pv   = acct.get("portfolio_value", 0)
cash = acct.get("cash", 0)
dpl  = acct.get("day_pl", 0)

# ── Top Bloomberg bar ─────────────────────────────────────────────────────────
_live_badge = (
    "<span style='font-size:8px;background:#3fb95020;color:#3fb950;"
    "border:1px solid #3fb95040;border-radius:2px;padding:1px 4px;"
    "font-family:IBM Plex Mono,monospace;vertical-align:middle;margin-left:4px'>LIVE</span>"
    if regime_source == "live" else
    "<span style='font-size:8px;background:#e3b34120;color:#e3b341;"
    "border:1px solid #e3b34140;border-radius:2px;padding:1px 4px;"
    "font-family:IBM Plex Mono,monospace;vertical-align:middle;margin-left:4px'>HIST</span>"
)
_brent_str = f"{brent_vol:.0%} vol" if brent_vol > 0 else ""

st.markdown(f"""
<div class="t-bar">
  <div class="t-card">
    <div class="lbl">Terminal</div>
    <div class="val teal">GEOSENTINEL</div>
  </div>
  <div class="t-card">
    <div class="lbl">Regime {_live_badge}</div>
    <div class="val {rc}">{regime_label.upper()} &nbsp;{regime_prob:.0%}</div>
    {"<div style='font-size:9px;color:#8b949e;font-family:IBM Plex Mono,monospace'>Brent " + _brent_str + "</div>" if _brent_str else ""}
  </div>
  <div class="t-card">
    <div class="lbl">Portfolio</div>
    <div class="val">${pv:,.2f}</div>
  </div>
  <div class="t-card">
    <div class="lbl">Day P&L</div>
    <div class="val {'green' if dpl >= 0 else 'red'}">${dpl:+,.2f}</div>
  </div>
  <div class="t-card">
    <div class="lbl">Buying Power</div>
    <div class="val">${cash:,.2f}</div>
  </div>
  <div class="t-card">
    <div class="lbl">Mode</div>
    <div class="val yellow">PAPER TRADING</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Tabs — imports deferred until render to avoid blocking cold start ─────────
t1, t2, t3, t4, t5 = st.tabs([
    "PORTFOLIO", "LIVE NEWS", "RESEARCH", "SCENARIO", "SETTINGS",
])

with t1:
    try:
        from src.tabs.tab3_portfolio import render as tab_portfolio
        tab_portfolio(demo_mode=DEMO_MODE)
    except Exception as _e:
        render_error_card("PORTFOLIO", _e)
with t2:
    try:
        from src.tabs.tab1_news import render as tab_news
        tab_news(demo_mode=DEMO_MODE)
    except Exception as _e:
        render_error_card("LIVE NEWS", _e)
with t3:
    try:
        from src.tabs.tab2_research import render as tab_research
        tab_research(demo_mode=DEMO_MODE)
    except Exception as _e:
        render_error_card("RESEARCH", _e)
with t4:
    try:
        from src.tabs.tab8_scenario import render as tab_scenario
        tab_scenario(demo_mode=DEMO_MODE)
    except Exception as _e:
        render_error_card("SCENARIO", _e)
with t5:
    try:
        from src.tabs.tab4_settings import render as tab_settings
        tab_settings(demo_mode=DEMO_MODE)
    except Exception as _e:
        render_error_card("SETTINGS", _e)
