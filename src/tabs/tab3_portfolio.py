"""
tab8_portfolio.py — GeoSentinel Terminal (VARTA)
Live Alpaca paper portfolio: holdings, P&L, regime stress test, trade execution.
Display code only — all data via fetchers.py and models/portfolio.py + trader.py.
"""

import json
import polars as pl
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timezone
from src.data.fetchers import (
    fetch_alpaca_portfolio, fetch_alpaca_account,
    fetch_recent_orders,
)
from src.data.loaders import load_prices, load_regimes
from src.models.portfolio import (
    compute_portfolio_pnl, compute_risk_metrics,
    regime_stress_test, efficient_frontier, optimize_weights,
)
from src.models.trader import generate_regime_orders, execute_strategy
from src.models.regime import get_current_regime
from src.utils import set_dark_theme, annotate_events
from src.db.settings_store import get_setting, set_setting
from config import ASSETS, TICKERS, TEAM_PALETTE, RISK_FREE_RATE


# ── Alert rules helpers ───────────────────────────────────────────────────────
_RULES_KEY = "alert_rules"


def _load_rules() -> list[dict]:
    """Load alert rules from SQLite. Returns list of rule dicts."""
    raw = get_setting(_RULES_KEY, default="[]")
    try:
        return json.loads(raw)
    except Exception:
        return []


def _save_rules(rules: list[dict]) -> None:
    """Persist alert rules to SQLite as JSON."""
    set_setting(_RULES_KEY, json.dumps(rules))


def _next_id(rules: list[dict]) -> int:
    """Return next available rule ID."""
    return max((r.get("id", 0) for r in rules), default=0) + 1


def _check_alerts(rules: list[dict]) -> list[dict]:
    """
    Evaluate all active alert rules against live data.
    Returns list of triggered alert dicts with added 'message' key.
    """
    if not rules:
        return []

    triggered = []
    prices_dict: dict[str, float] = {}
    regime_label = "Normal"
    regime_prob  = 0.0

    try:
        from src.data.fetchers import fetch_live_prices
        prices_df = fetch_live_prices(TICKERS)
        if not prices_df.is_empty():
            latest = prices_df.sort("date", descending=True).group_by("ticker").first()
            prices_dict = dict(zip(latest["ticker"].to_list(), latest["close"].to_list()))
    except Exception:
        pass

    try:
        from src.models.regime_live import get_live_regime
        ri = get_live_regime()
        regime_label = ri.get("label", "Normal")
        regime_prob  = ri.get("prob", 0.0)
    except Exception:
        pass

    for rule in rules:
        if not rule.get("active", True):
            continue
        rtype = rule.get("type", "")
        try:
            if rtype == "regime_change":
                target = rule.get("threshold", "Crisis")
                if regime_label == target:
                    triggered.append({**rule, "message":
                        f"REGIME ALERT: VARTA regime is now {regime_label} "
                        f"(P={regime_prob:.0%})"})
            elif rtype == "price_cross":
                tkr   = rule.get("ticker", "SPY")
                level = float(rule.get("threshold", 0))
                dirn  = rule.get("direction", "above")
                price = prices_dict.get(tkr)
                if price is not None:
                    hit = (price >= level and dirn == "above") or \
                          (price <= level and dirn == "below")
                    if hit:
                        triggered.append({**rule, "message":
                            f"PRICE ALERT: {tkr} is ${price:.2f} "
                            f"({'above' if dirn=='above' else 'below'} ${level:.2f})"})
            elif rtype == "drawdown":
                tkr    = rule.get("ticker", "SPY")
                max_dd = float(rule.get("threshold", 5.0)) / 100
                price  = prices_dict.get(tkr)
                peak_key = f"alert_peak_{tkr}"
                if price is not None:
                    peak = st.session_state.get(peak_key, price)
                    st.session_state[peak_key] = max(peak, price)
                    current_dd = (price - peak) / peak if peak > 0 else 0
                    if current_dd <= -max_dd:
                        triggered.append({**rule, "message":
                            f"DRAWDOWN ALERT: {tkr} is down {current_dd:.1%} "
                            f"from recent peak (trigger: {-max_dd:.1%})"})
        except Exception:
            pass

    return triggered


@st.fragment(run_every=120)
def _alerts_fragment() -> None:
    """Auto-refresh alert checker — runs every 120s."""
    rules     = _load_rules()
    triggered = _check_alerts(rules)

    if triggered:
        for alert in triggered:
            msg  = alert.get("message", "Alert triggered")
            at   = alert.get("type", "")
            icon = "🔴" if at == "regime_change" else "📊" if at == "price_cross" else "📉"
            st.markdown(
                f"<div style='background:#f8514918;border:1px solid #f85149;"
                f"border-radius:6px;padding:12px 16px;margin-bottom:8px'>"
                f"<span style='font-family:IBM Plex Mono,monospace;font-size:12px;"
                f"color:#f85149;font-weight:700'>{icon} {msg}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            "<div style='background:#3fb95015;border:1px solid #3fb95040;"
            "border-radius:6px;padding:10px 16px;font-family:IBM Plex Mono,monospace;"
            "font-size:11px;color:#3fb950'>✓ No alerts triggered — all clear</div>",
            unsafe_allow_html=True,
        )
    st.caption(
        f"Last checked: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')} "
        "· Auto-refreshes every 120s"
    )


def render(demo_mode: bool = True) -> None:
    """Render the Portfolio & Trade Execution tab."""

    st.subheader("Portfolio & Regime Trading")
    st.caption("Live Alpaca paper account · Regime-aware rebalancing · No real money")

    # ── Load data ─────────────────────────────────────────────────────────────
    positions = fetch_alpaca_portfolio()
    account   = fetch_alpaca_account()
    hist_returns = load_prices(demo_mode)
    regimes_df   = load_regimes(demo_mode)
    regime_info  = st.session_state.get("regime_info") or get_current_regime(demo_mode)

    # ── Account header ────────────────────────────────────────────────────────
    if account:
        pv   = account.get("portfolio_value", 0)
        cash = account.get("cash", 0)
        dpl  = account.get("day_pl", 0)
        dpct = account.get("day_pl_pct", 0)
        bp   = account.get("buying_power", 0)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Portfolio Value",  f"${pv:,.2f}")
        col2.metric("Cash Available",   f"${cash:,.2f}")
        col3.metric("Day P&L",          f"${dpl:+,.2f}", f"{dpct:+.2f}%")
        col4.metric("Buying Power",     f"${bp:,.2f}")
    else:
        st.warning("Could not connect to Alpaca. Check your API keys in Settings.")
        _show_seed_instructions()
        return

    st.divider()

    # ── Current regime banner ─────────────────────────────────────────────────
    regime_label  = regime_info.get("label", "Normal")
    regime_prob   = regime_info.get("prob", 0.0)
    regime_source = regime_info.get("source", "live")
    regime_color  = "#EF4444" if regime_label == "Crisis" else "#e3b341" if regime_label == "Elevated" else "#22C55E"

    # Build live signal detail string
    _brent   = regime_info.get("brent_vol", 0)
    _spy_dd  = regime_info.get("spy_dd", 0)
    _go      = regime_info.get("gold_oil", 0)
    _src_lbl = "LIVE SIGNAL" if regime_source == "live" else "HISTORICAL"
    _detail  = (
        f"Brent Vol {_brent:.0%} · SPY DD {_spy_dd:.1%} · Gold/Oil {_go:.1f}"
        if regime_source == "live" and _brent > 0 else
        f"as of {regime_info.get('date','—')}"
    )

    st.markdown(
        f"<div style='background:{regime_color}18;border-left:4px solid {regime_color};"
        f"padding:10px 16px;border-radius:4px;margin-bottom:16px;display:flex;"
        f"justify-content:space-between;align-items:center;flex-wrap:wrap'>"
        f"<div>"
        f"<b style='color:{regime_color};font-size:16px'>VARTA REGIME: {regime_label.upper()}</b>"
        f"&nbsp;&nbsp;·&nbsp;&nbsp;P(Crisis) = <b>{regime_prob:.0%}</b>"
        f"</div>"
        f"<div style='font-family:IBM Plex Mono,monospace;font-size:10px;color:#8b949e'>"
        f"<span style='color:{regime_color};margin-right:6px'>{_src_lbl}</span>{_detail}"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Holdings table ────────────────────────────────────────────────────────
    st.markdown("### Current Holdings")

    if positions.is_empty():
        st.info("No open positions found. Buy some assets in your Alpaca paper account first.")
        _show_seed_instructions()
        return

    positions = compute_portfolio_pnl(positions)

    # Format for display
    display = positions.select([
        pl.col("ticker"),
        pl.col("qty").round(2).alias("Shares"),
        pl.col("avg_entry_price").map_elements(lambda x: f"${x:,.2f}", return_dtype=pl.Utf8).alias("Avg Cost"),
        pl.col("current_price").map_elements(lambda x: f"${x:,.2f}", return_dtype=pl.Utf8).alias("Price"),
        pl.col("market_value").map_elements(lambda x: f"${x:,.2f}", return_dtype=pl.Utf8).alias("Mkt Value"),
        pl.col("unrealized_pl").map_elements(lambda x: f"${x:+,.2f}", return_dtype=pl.Utf8).alias("Unrealized P&L"),
        pl.col("unrealized_plpc").map_elements(lambda x: f"{x:+.1f}%", return_dtype=pl.Utf8).alias("P&L %"),
        pl.col("weight_pct").map_elements(lambda x: f"{x:.1f}%", return_dtype=pl.Utf8).alias("Weight"),
    ]).rename({"ticker": "Ticker"})

    st.dataframe(display, width="stretch", hide_index=True)

    # ── Portfolio composition chart ───────────────────────────────────────────
    st.markdown("### Portfolio Allocation")
    fig_pie = go.Figure(go.Pie(
        labels=positions["ticker"].to_list(),
        values=positions["market_value"].to_list(),
        hole=0.45,
        marker=dict(colors=[
            next((v for k, v in TEAM_PALETTE.items()
                  if k in ASSETS.get(t, {}).get("category", "")), "#94A3B8")
            for t in positions["ticker"].to_list()
        ]),
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>Value: $%{value:,.0f}<br>Weight: %{percent}<extra></extra>",
    ))
    fig_pie = set_dark_theme(fig_pie)
    fig_pie.update_layout(height=380, showlegend=False,
                          annotations=[dict(text=f"${account.get('portfolio_value',0):,.0f}",
                                           font_size=16, showarrow=False)])
    st.plotly_chart(fig_pie, width="stretch")

    # ── Risk metrics ──────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### Portfolio Risk Metrics")

    weights_dict: dict = {}
    metrics: dict = {}

    if not hist_returns.is_empty():
        weights_dict = {
            row["ticker"]: row["weight_pct"] / 100
            for row in positions.to_dicts()
            if row["ticker"] in hist_returns["ticker"].unique().to_list()
        }
        if weights_dict:
            metrics = compute_risk_metrics(weights_dict, hist_returns)
            if metrics:
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Annual Return",  f"{metrics['annual_return']*100:+.1f}%")
                m2.metric("Annual Vol",     f"{metrics['annual_vol']*100:.1f}%")
                m3.metric("Sharpe Ratio",   f"{metrics['sharpe']:.2f}")
                m4.metric("Sortino Ratio",  f"{metrics['sortino']:.2f}")
                m5, m6, m7, m8 = st.columns(4)
                m5.metric("Max Drawdown",   f"{metrics['max_drawdown']*100:.1f}%")
                m6.metric("VaR 95% (1D)",   f"{metrics['var_95']*100:.2f}%")
                m7.metric("CVaR 95% (1D)",  f"{metrics['cvar_95']*100:.2f}%")
                m8.metric("Beta vs SPY",    f"{metrics['beta_spy']:.2f}")

    # ── Regime stress test ────────────────────────────────────────────────────
    st.markdown("### Regime Stress Test")
    st.caption("How your portfolio performs in Crisis vs Normal regime — based on 2010–2024 historical data")

    if not hist_returns.is_empty() and not regimes_df.is_empty() and weights_dict:
        stress = regime_stress_test(weights_dict, hist_returns, regimes_df)
        if not stress.is_empty():
            st.dataframe(stress, width="stretch", hide_index=True)

    # ── Efficient frontier — gated behind a button to avoid 500-portfolio MC on every render
    with st.expander("Efficient Frontier (Monte Carlo — 500 portfolios)"):
        held_tickers = positions["ticker"].to_list()
        valid = [t for t in held_tickers if t in (hist_returns["ticker"].unique().to_list() if not hist_returns.is_empty() else [])]
        _ef_key = f"ef_{sorted(valid)}"
        if len(valid) >= 2:
            if _ef_key not in st.session_state:
                if st.button("Generate Efficient Frontier", key="btn_ef"):
                    with st.spinner("Running Monte Carlo (500 portfolios)..."):
                        st.session_state[_ef_key] = efficient_frontier(hist_returns, valid)
                else:
                    st.caption("Click to generate the efficient frontier for your current holdings.")
            frontier = st.session_state.get(_ef_key, pl.DataFrame())
            if not frontier.is_empty():
                fig_ef = go.Figure(go.Scatter(
                    x=frontier["vol"].to_list(),
                    y=frontier["ret"].to_list(),
                    mode="markers",
                    marker=dict(
                        color=frontier["sharpe"].to_list(),
                        colorscale="Viridis",
                        size=5,
                        colorbar=dict(title="Sharpe"),
                    ),
                    hovertemplate="Vol: %{x:.1%}<br>Ret: %{y:.1%}<extra></extra>",
                ))
                # Mark current portfolio
                if metrics:
                    fig_ef.add_trace(go.Scatter(
                        x=[metrics["annual_vol"]],
                        y=[metrics["annual_return"]],
                        mode="markers+text",
                        marker=dict(color="#00FFB2", size=14, symbol="star"),
                        text=["Your Portfolio"],
                        textposition="top center",
                        name="Current",
                    ))
                fig_ef = set_dark_theme(fig_ef)
                fig_ef.update_layout(
                    height=400,
                    xaxis_title="Annual Volatility",
                    yaxis_title="Annual Return",
                    xaxis=dict(tickformat=".0%"),
                    yaxis=dict(tickformat=".0%"),
                    showlegend=False,
                )
                st.plotly_chart(fig_ef, width="stretch")

    # ── Regime trade recommendations ──────────────────────────────────────────
    st.divider()
    st.markdown("### Regime Rebalancing Engine")
    st.caption("Orders generated from VARTA regime signal × historical regime-conditional returns")

    strategy = st.selectbox(
        "Optimization strategy",
        ["regime_target", "max_sharpe", "min_variance"],
        format_func=lambda x: {
            "regime_target": "Regime Target Weights (from VARTA historical analysis)",
            "max_sharpe":    "Max Sharpe Ratio (regime-filtered)",
            "min_variance":  "Minimum Variance (regime-filtered)",
        }[x],
    )

    total_equity = account.get("equity", account.get("portfolio_value", 0))

    orders = generate_regime_orders(
        positions=positions,
        regime=regime_label,
        regime_prob=regime_prob,
        returns_df=hist_returns,
        regimes_df=regimes_df,
        total_equity=total_equity,
        method=strategy,
    )

    if orders.is_empty():
        st.success("Portfolio already aligned with regime targets — no rebalancing needed.")
    else:
        # Format orders for display
        orders_display = orders.select([
            pl.col("ticker").alias("Ticker"),
            pl.col("action").alias("Action"),
            pl.col("order_qty").round(1).alias("Shares"),
            pl.col("current_price").map_elements(lambda x: f"${x:,.2f}", return_dtype=pl.Utf8).alias("Price"),
            pl.col("current_weight_pct").map_elements(lambda x: f"{x:.1f}%", return_dtype=pl.Utf8).alias("Current Wt"),
            pl.col("target_weight_pct").map_elements(lambda x: f"{x:.1f}%", return_dtype=pl.Utf8).alias("Target Wt"),
            pl.col("estimated_value").map_elements(lambda x: f"${x:,.0f}", return_dtype=pl.Utf8).alias("Est. Value"),
            pl.col("rationale").alias("Rationale"),
        ])
        st.dataframe(orders_display, width="stretch", hide_index=True)

        # ── Two-step order confirmation (safety gate) ─────────────────────────
        _confirm_key = "order_confirm_pending"

        if not st.session_state.get(_confirm_key, False):
            col_exec, col_reset = st.columns([1, 4])
            with col_exec:
                if st.button("Confirm Order", type="primary",
                             help="Review order details before executing"):
                    st.session_state[_confirm_key] = True
                    st.rerun()
            with col_reset:
                st.caption("Paper trading only — no real money. Click Confirm Order to review before executing.")
        else:
            st.warning("Review the orders above carefully. This action cannot be undone.")
            with st.expander("Order Summary", expanded=True):
                st.dataframe(orders_display, width="stretch", hide_index=True)
                total_est = orders["estimated_value"].sum()
                st.markdown(
                    f"<div style='font-family:IBM Plex Mono,monospace;font-size:12px;"
                    f"color:#e3b341;margin-top:8px'>Estimated total trade value: "
                    f"<b>${total_est:,.0f}</b></div>",
                    unsafe_allow_html=True,
                )

            col_yes, col_no, _ = st.columns([1, 1, 3])
            with col_yes:
                if st.button("YES, EXECUTE", type="primary"):
                    st.session_state[_confirm_key] = False
                    with st.spinner("Executing paper trades..."):
                        results = execute_strategy(orders)
                    if not results.is_empty():
                        st.success(f"Strategy executed — {len(results)} orders placed")
                        st.dataframe(results, width="stretch", hide_index=True)
                        fetch_alpaca_portfolio.clear()
                        fetch_alpaca_account.clear()
                        st.rerun()
            with col_no:
                if st.button("Cancel", type="secondary"):
                    st.session_state[_confirm_key] = False
                    st.rerun()

    # ── Recent orders log ─────────────────────────────────────────────────────
    with st.expander("Order History (last 20)"):
        recent = fetch_recent_orders(limit=20)
        if not recent.is_empty():
            st.dataframe(recent, width="stretch", hide_index=True)
        else:
            st.caption("No orders yet.")

    # ── Alerts Engine ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### Alerts Engine")
    st.caption("Price, regime, and drawdown alerts · Auto-checks every 120s · Stored across sessions")

    rules = _load_rules()

    st.markdown("#### Live Alert Status")
    _alerts_fragment()

    st.divider()
    st.markdown("#### Add Alert Rule")

    with st.form("add_alert_form", clear_on_submit=True):
        col_type, col_ticker = st.columns(2)
        with col_type:
            rule_type = st.selectbox(
                "Alert Type",
                ["price_cross", "regime_change", "drawdown"],
                format_func=lambda x: {
                    "price_cross":   "Price Cross (above/below level)",
                    "regime_change": "Regime Change (Crisis or Normal)",
                    "drawdown":      "Drawdown from Peak (%)",
                }[x],
            )
        with col_ticker:
            ticker_alert = st.selectbox(
                "Ticker", TICKERS,
                help="Not required for regime_change alerts",
            )

        col_thresh, col_dir = st.columns(2)
        with col_thresh:
            threshold = st.number_input(
                "Threshold", value=100.0,
                help="Price level (price_cross), drawdown % (drawdown), or ignored (regime_change)",
            )
        with col_dir:
            direction = st.selectbox(
                "Direction / Target Regime",
                ["above", "below", "Crisis", "Normal"],
                help="above/below for price_cross; Crisis/Normal for regime_change",
            )

        submitted = st.form_submit_button("Add Alert", type="primary")
        if submitted:
            new_rule = {
                "id":         _next_id(rules),
                "type":       rule_type,
                "ticker":     ticker_alert,
                "threshold":  threshold,
                "direction":  direction,
                "active":     True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            rules.append(new_rule)
            _save_rules(rules)
            st.success(f"Alert added: {rule_type} on {ticker_alert}")
            st.rerun()

    if rules:
        st.divider()
        st.markdown("#### Active Alert Rules")
        for rule in rules:
            col_info, col_toggle, col_del = st.columns([5, 1, 1])
            with col_info:
                rt = rule.get("type", "")
                if rt == "price_cross":
                    desc = (f"**{rule.get('ticker','—')}** "
                            f"{rule.get('direction','above')} "
                            f"${rule.get('threshold',0):.2f}")
                elif rt == "regime_change":
                    desc = f"Regime → **{rule.get('direction','Crisis')}**"
                else:
                    desc = (f"**{rule.get('ticker','—')}** drawdown ≥ "
                            f"{rule.get('threshold',5):.1f}%")
                status = "🟢 Active" if rule.get("active", True) else "⚫ Paused"
                st.markdown(
                    f"{status} &nbsp; {desc} &nbsp; "
                    f"<span style='font-size:10px;color:#8b949e'>#{rule.get('id',0)}</span>",
                    unsafe_allow_html=True,
                )
            with col_toggle:
                lbl = "Pause" if rule.get("active", True) else "Resume"
                if st.button(lbl, key=f"ptog_{rule['id']}"):
                    for r in rules:
                        if r["id"] == rule["id"]:
                            r["active"] = not r.get("active", True)
                    _save_rules(rules)
                    st.rerun()
            with col_del:
                if st.button("Delete", key=f"pdel_{rule['id']}"):
                    rules = [r for r in rules if r["id"] != rule["id"]]
                    _save_rules(rules)
                    st.rerun()


def _show_seed_instructions() -> None:
    """Show instructions for seeding the Alpaca paper account."""
    st.markdown("""
    **Seed your paper portfolio** — go to [app.alpaca.markets](https://app.alpaca.markets)
    and manually buy these positions to get started:

    | Ticker | Amount |
    |--------|--------|
    | NVDA | $12,000 |
    | TSM  | $10,000 |
    | SPY  | $10,000 |
    | GLD  | $8,000  |
    | REMX | $8,000  |
    | LIT  | $7,000  |
    | XOM  | $7,000  |
    | FCX  | $7,000  |
    | ALB  | $6,000  |
    | AMD  | $6,000  |
    | CVX  | $5,000  |
    | BNO  | $4,000  |
    """)
