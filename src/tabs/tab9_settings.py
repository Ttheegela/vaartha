"""
tab9_settings.py — GeoSentinel Terminal (VARTA)
User settings: Alpaca API credentials, strategy preferences, regime thresholds.
Credentials stored in st.session_state only — never written to disk or logged.
"""

import streamlit as st
from config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY,
    GEORISK_SENSITIVITY, REGIME_TARGET_WEIGHTS, ASSETS, TICKERS,
)


# ── Session state defaults ────────────────────────────────────────────────────
def _init_state() -> None:
    """Initialize session state with config.py defaults on first load."""
    if "user_alpaca_key"    not in st.session_state:
        st.session_state.user_alpaca_key    = ALPACA_API_KEY
    if "user_alpaca_secret" not in st.session_state:
        st.session_state.user_alpaca_secret = ALPACA_SECRET_KEY
    if "user_paper_mode"    not in st.session_state:
        st.session_state.user_paper_mode    = True
    if "user_tickers"       not in st.session_state:
        st.session_state.user_tickers       = TICKERS[:]
    if "user_risk_tolerance" not in st.session_state:
        st.session_state.user_risk_tolerance = "Moderate"
    if "user_strategy"      not in st.session_state:
        st.session_state.user_strategy      = "regime_target"
    if "user_rebalance_threshold" not in st.session_state:
        st.session_state.user_rebalance_threshold = 5.0
    if "settings_saved"     not in st.session_state:
        st.session_state.settings_saved     = False


def get_active_keys() -> tuple[str, str]:
    """Return the currently active Alpaca keys (session override or config default)."""
    _init_state()
    return (
        st.session_state.user_alpaca_key    or ALPACA_API_KEY,
        st.session_state.user_alpaca_secret or ALPACA_SECRET_KEY,
    )


def get_active_tickers() -> list[str]:
    """Return the currently selected ticker universe."""
    _init_state()
    return st.session_state.user_tickers or TICKERS


def render(demo_mode: bool = True) -> None:
    """Render the Settings tab."""
    _init_state()

    st.markdown("### Terminal Settings")
    st.caption("Configure your Alpaca account, asset universe, and strategy preferences")

    # ── Section 1: Alpaca credentials ────────────────────────────────────────
    st.markdown("#### Brokerage Connection")
    st.html(
        "<div style='background:#161b22;border:1px solid #30363d;border-radius:6px;"
        "padding:12px 16px;margin-bottom:16px;font-family:IBM Plex Mono,monospace;"
        "font-size:10px;color:#8b949e'>"
        "Keys are stored in memory only for this session — never saved to disk or logged. "
        "Use your Alpaca Paper Trading keys from "
        "<a href='https://app.alpaca.markets' target='_blank' style='color:#58a6ff'>"
        "app.alpaca.markets</a> → Account → API Keys."
        "</div>"
    )

    col1, col2 = st.columns(2)
    with col1:
        new_key = st.text_input(
            "Alpaca API Key",
            value=st.session_state.user_alpaca_key,
            type="password",
            placeholder="PKSQ...",
            help="From Alpaca dashboard → Account → API Keys",
        )
    with col2:
        new_secret = st.text_input(
            "Alpaca Secret Key",
            value=st.session_state.user_alpaca_secret,
            type="password",
            placeholder="6o9U...",
        )

    paper_mode = st.checkbox(
        "Paper Trading Mode (recommended — no real money)",
        value=st.session_state.user_paper_mode,
    )

    # Connection test
    col_save, col_test, _ = st.columns([1, 1, 3])
    with col_save:
        if st.button("Save Credentials", type="primary"):
            st.session_state.user_alpaca_key    = new_key
            st.session_state.user_alpaca_secret = new_secret
            st.session_state.user_paper_mode    = paper_mode
            st.session_state.settings_saved     = True
            # Clear portfolio cache so next load uses new keys
            try:
                from src.data.fetchers import fetch_alpaca_portfolio, fetch_alpaca_account
                fetch_alpaca_portfolio.clear()
                fetch_alpaca_account.clear()
            except Exception:
                pass
            st.success("Credentials saved for this session.")

    with col_test:
        if st.button("Test Connection"):
            with st.spinner("Connecting to Alpaca..."):
                try:
                    from alpaca.trading.client import TradingClient
                    client = TradingClient(
                        api_key=new_key or ALPACA_API_KEY,
                        secret_key=new_secret or ALPACA_SECRET_KEY,
                        paper=paper_mode,
                    )
                    acct = client.get_account()
                    pv   = float(acct.portfolio_value)
                    st.success(f"Connected — Portfolio value: ${pv:,.2f}")
                except Exception as e:
                    st.error(f"Connection failed: {e}")

    st.divider()

    # ── Section 2: Asset universe ─────────────────────────────────────────────
    st.markdown("#### Asset Universe")
    st.caption("Select which tickers the terminal tracks, news filters to, and risk scores compute for")

    # Group assets by category for cleaner display
    by_cat: dict[str, list[str]] = {}
    for tkr, info in ASSETS.items():
        cat = info.get("category", "Other")
        by_cat.setdefault(cat, []).append(tkr)

    cat_cols = st.columns(3)
    for i, (cat, tkrs) in enumerate(sorted(by_cat.items())):
        with cat_cols[i % 3]:
            st.markdown(f"**{cat}**")
            for tkr in tkrs:
                name = ASSETS[tkr]["name"]
                # Use default= only on first render; subsequent renders read from
                # st.session_state[f"asset_{tkr}"] automatically (Streamlit standard)
                st.checkbox(
                    f"{tkr} — {name}",
                    value=tkr in st.session_state.user_tickers,
                    key=f"asset_{tkr}",
                )

    if st.button("Apply Asset Selection"):
        # Read current checkbox state from session_state keys (no snap-back)
        selected = [tkr for tkr in ASSETS if st.session_state.get(f"asset_{tkr}", False)]
        if not selected:
            st.warning("Select at least one asset.")
        else:
            st.session_state.user_tickers = selected
            st.success(f"Tracking {len(selected)} assets: {', '.join(selected)}")

    st.divider()

    # ── Section 3: Strategy preferences ──────────────────────────────────────
    st.markdown("#### Strategy Preferences")

    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        risk_tolerance = st.selectbox(
            "Risk Tolerance",
            ["Conservative", "Moderate", "Aggressive"],
            index=["Conservative", "Moderate", "Aggressive"].index(
                st.session_state.user_risk_tolerance
            ),
            help=(
                "Conservative: overweight GLD/SPY in crisis. "
                "Aggressive: hold semiconductor/EM in all regimes."
            ),
        )
    with sc2:
        strategy = st.selectbox(
            "Rebalancing Strategy",
            ["regime_target", "max_sharpe", "min_variance"],
            index=["regime_target", "max_sharpe", "min_variance"].index(
                st.session_state.user_strategy
            ),
            format_func=lambda x: {
                "regime_target": "Regime Target (VARTA default)",
                "max_sharpe":    "Max Sharpe Ratio",
                "min_variance":  "Minimum Variance",
            }[x],
        )
    with sc3:
        threshold = st.slider(
            "Rebalance Trigger (% drift)",
            min_value=1.0,
            max_value=15.0,
            value=st.session_state.user_rebalance_threshold,
            step=0.5,
            help="Only rebalance when a position drifts this far from its target weight",
        )

    # Show target weights for selected strategy + risk tolerance
    _regime_key = "Crisis" if risk_tolerance == "Conservative" else "Normal"
    target_weights = REGIME_TARGET_WEIGHTS.get(_regime_key, {})

    if target_weights:
        st.markdown(f"**Preview: {risk_tolerance} · {_regime_key} regime target weights**")
        wt_cols = st.columns(6)
        for i, (tkr, wt) in enumerate(
            sorted(target_weights.items(), key=lambda x: x[1], reverse=True)
        ):
            with wt_cols[i % 6]:
                color = "#f85149" if wt >= 0.15 else "#e3b341" if wt >= 0.08 else "#8b949e"
                st.html(
                    f"<div style='text-align:center;padding:8px;background:#161b22;"
                    f"border:1px solid #30363d;border-radius:5px'>"
                    f"<div style='font-size:11px;font-weight:700;color:#00FFB2;"
                    f"font-family:IBM Plex Mono,monospace'>{tkr}</div>"
                    f"<div style='font-size:14px;font-weight:700;color:{color}'>"
                    f"{wt*100:.0f}%</div></div>"
                )

    if st.button("Save Strategy Settings", type="primary"):
        st.session_state.user_risk_tolerance       = risk_tolerance
        st.session_state.user_strategy             = strategy
        st.session_state.user_rebalance_threshold  = threshold
        st.success("Strategy settings saved for this session.")

    st.divider()

    # ── Section 4: GeoRisk sensitivity editor ────────────────────────────────
    st.markdown("#### GeoRisk Sensitivity Weights")
    st.caption(
        "How sensitive each asset is to geopolitical shocks. "
        "1.40 = maximum (Taiwan Strait). 0.55 = minimum (Gold safe haven). "
        "Affects the GeoRisk Score shown in the Research tab."
    )

    sens_cols = st.columns(4)
    for i, (tkr, default_sens) in enumerate(sorted(GEORISK_SENSITIVITY.items())):
        with sens_cols[i % 4]:
            st.slider(
                tkr,
                min_value=0.1,
                max_value=2.0,
                value=float(default_sens),
                step=0.05,
                format="%.2f",
                key=f"sens_{tkr}",
                help=ASSETS.get(tkr, {}).get("name", tkr),
                disabled=True,   # read-only for now — shows values, not editable mid-session
            )

    st.caption("Sensitivity values are derived from VARTA's historical causal chain analysis (2010–2024).")

    st.divider()

    # ── Section 5: About ──────────────────────────────────────────────────────
    st.markdown("#### About GeoSentinel Terminal")
    st.html(
        "<div style='background:#161b22;border:1px solid #30363d;border-radius:6px;"
        "padding:16px;font-family:IBM Plex Mono,monospace;font-size:11px;line-height:1.8'>"
        "<div style='color:#00FFB2;font-size:14px;font-weight:700;margin-bottom:8px'>"
        "GEOSENTINEL TERMINAL v1.0</div>"
        "<div style='color:#c9d1d9;margin-top:8px'>"
        "Regime detection engine trained on 14 geopolitical events (2010–2024). "
        "Live signals via Brent Oil volatility proxy. "
        "Paper trading via Alpaca. News via Alpaca + Finnhub. "
        "Crowd signals via Polymarket.</div>"
        "<div style='color:#8b949e;margin-top:8px'>"
        "github.com/Ttheegela/vaartha</div>"
        "</div>"
    )
