"""
app.py — GeoSentinel Terminal (VARTA)
Streamlit entry point. Wires up the 5 dashboard tabs.
Run: streamlit run app.py
"""

import streamlit as st
from config import DEMO_MODE

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GeoSentinel Terminal",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Dark Bloomberg-style CSS ──────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #0a0a0a; color: #e2e8f0; }
    .stTabs [data-baseweb="tab"] { background-color: #1a1a2e; color: #94a3b8; }
    .stTabs [aria-selected="true"] { background-color: #16213e; color: #00FFB2; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## GeoSentinel Terminal")
    st.markdown("*Regime-Aware Geopolitical Risk Intelligence*")
    st.divider()
    demo = st.toggle("Demo Mode (offline)", value=DEMO_MODE)
    st.caption("Team 7 Lambda · Rutgers SP2026")

# ── Tab imports (deferred to avoid load time on startup) ─────────────────────
from src.tabs.tab1_watchlist  import render as tab1
from src.tabs.tab2_crisis_timeline import render as tab2
from src.tabs.tab3_regime     import render as tab3
from src.tabs.tab4_signals    import render as tab4
from src.tabs.tab5_maps       import render as tab5

# ── Tabs ──────────────────────────────────────────────────────────────────────
t1, t2, t3, t4, t5 = st.tabs([
    "📊 Portfolio Watchlist",
    "📅 Crisis Timeline",
    "🔄 Regime Engine",
    "📈 Return Signals",
    "🗺️ Supply Chain Geography",
])

with t1: tab1(demo_mode=demo)
with t2: tab2(demo_mode=demo)
with t3: tab3(demo_mode=demo)
with t4: tab4(demo_mode=demo)
with t5: tab5(demo_mode=demo)
