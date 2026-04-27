"""
tab3_regime.py — Regime Engine
HMM/GMM regime detection visualization + transparent 6-model quantitative risk stack.
Display code only — all data access goes through loaders.py.
"""

import polars as pl
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from src.data.loaders import load_prices, load_fred, load_regimes
from src.models.regime import get_current_regime, get_regime_stats, get_regime_conditional_returns
from src.utils import set_dark_theme, annotate_events
from config import REGIME_CRISIS, REGIME_NORMAL, TEAM_PALETTE, TICKERS, ASSETS


def render(demo_mode: bool = True) -> None:
    """Render the Regime Engine tab."""
    st.subheader("Regime Engine")
    st.caption("Hidden Markov Model · Gaussian Mixture Model · 2010–2024 historical regimes")

    regimes = load_regimes(demo_mode)
    prices  = load_prices(demo_mode)
    fred    = load_fred(demo_mode)

    if regimes.is_empty():
        st.warning("No regime data available. Run regime detection notebook first.")
        return

    # ── Current regime + stats ────────────────────────────────────────────────
    regime_info = get_current_regime(demo_mode)
    stats       = get_regime_stats(demo_mode)

    label_color = "#EF4444" if regime_info["label"] == REGIME_CRISIS else "#22C55E"
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Current Regime", regime_info["label"])
    c2.metric("Crisis Probability", f"{regime_info['prob']:.0%}")
    c3.metric("Crisis Days (2010–2024)", f"{stats.get('n_crisis_days', '—'):,}")
    c4.metric("Crisis Episodes", stats.get("n_episodes", "—"))

    st.markdown(
        f"<div style='background:{label_color}22;border-left:4px solid {label_color};"
        f"padding:6px 14px;border-radius:4px;margin:8px 0'>"
        f"Crisis: {stats.get('crisis_pct', '—')}% of training window · "
        f"Avg episode: {stats.get('avg_crisis_duration_days', '—')} days</div>",
        unsafe_allow_html=True,
    )

    # ── Regime probability time series ────────────────────────────────────────
    st.markdown("### Crisis Regime Probability (2010–2024)")
    reg = regimes.sort("date")
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=reg["date"].to_list(),
        y=reg["regime_prob"].to_list(),
        name="Crisis Prob",
        line=dict(color="#EF4444", width=1.5),
        fill="tozeroy",
        fillcolor="rgba(239,68,68,0.12)",
    ))
    fig.add_hline(y=0.5, line_dash="dash", line_color="#94A3B8", annotation_text="50% threshold")

    fig = set_dark_theme(fig)
    fig = annotate_events(fig)
    fig.update_layout(
        height=320,
        xaxis_title="Date",
        yaxis_title="Crisis Probability",
        yaxis=dict(range=[0, 1]),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Regime label overlay on SPY ────────────────────────────────────────────
    if not prices.is_empty():
        st.markdown("### SPY Price with Regime Shading")
        spy = prices.filter(pl.col("ticker") == "SPY").sort("date")
        if not spy.is_empty():
            fig2 = go.Figure(go.Scatter(
                x=spy["date"].to_list(),
                y=spy["close"].to_list(),
                name="SPY",
                line=dict(color="#94A3B8", width=1.5),
            ))
            # Crisis shading
            dates_r  = reg["date"].to_list()
            labels_r = reg["regime_label"].to_list()
            start = None
            for d, lbl in zip(dates_r, labels_r):
                if lbl == REGIME_CRISIS and start is None:
                    start = d
                elif lbl != REGIME_CRISIS and start is not None:
                    fig2.add_vrect(
                        x0=start, x1=d,
                        fillcolor="#EF4444", opacity=0.12,
                        layer="below", line_width=0,
                        annotation_text="Crisis", annotation_font_size=8,
                    )
                    start = None
            if start is not None:
                fig2.add_vrect(
                    x0=start, x1=dates_r[-1],
                    fillcolor="#EF4444", opacity=0.12,
                    layer="below", line_width=0,
                )
            fig2 = set_dark_theme(fig2)
            fig2 = annotate_events(fig2)
            fig2.update_layout(height=300, xaxis_title="Date", yaxis_title="SPY Close", hovermode="x unified")
            st.plotly_chart(fig2, use_container_width=True)

    # ── Regime-conditional return distributions ────────────────────────────────
    st.markdown("### Regime-Conditional Mean Returns (all 12 assets)")
    cond = get_regime_conditional_returns(demo_mode)

    if not cond.is_empty():
        crisis_df = cond.filter(pl.col("regime_label") == REGIME_CRISIS).sort("mean_return")
        normal_df = cond.filter(pl.col("regime_label") == REGIME_NORMAL).sort("mean_return")

        fig3 = go.Figure()
        if not crisis_df.is_empty():
            fig3.add_trace(go.Bar(
                name="Crisis regime",
                x=crisis_df["ticker"].to_list(),
                y=(crisis_df["mean_return"] * 100).to_list(),
                marker_color="#EF4444",
            ))
        if not normal_df.is_empty():
            fig3.add_trace(go.Bar(
                name="Normal regime",
                x=normal_df["ticker"].to_list(),
                y=(normal_df["mean_return"] * 100).to_list(),
                marker_color="#22C55E",
            ))

        fig3 = set_dark_theme(fig3)
        fig3.update_layout(
            height=360,
            barmode="group",
            xaxis_title="Ticker",
            yaxis_title="Mean 1-Day Return (%)",
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig3, use_container_width=True)

    # ── 6-model quant risk stack ──────────────────────────────────────────────
    st.divider()
    st.markdown("### Quantitative Risk Stack")
    st.caption("Six risk models — all trained on 2010–2024 Crisis/Normal regime labels")

    risk_models = [
        ("Bayesian Regime Posterior", "P(Crisis | GPR, GSCPI, Brent Vol) — conjugate beta update", "regime_prob from HMM"),
        ("Edge Ratio", "Mean Crisis return / Mean Normal return per asset", "cond. returns above"),
        ("Bid-Ask Spread Proxy", "Return std-dev ratio Crisis/Normal — liquidity stress proxy", "from prices.parquet"),
        ("Stoikov Inventory Risk", "Volatility-weighted regime exposure score", "crisis_pct × vol"),
        ("Kelly Criterion", "Optimal bet fraction given regime-conditional win rate", "from XGBoost signals"),
        ("Monte Carlo VaR", "95th pct drawdown distribution, regime-stratified", "10K simulated paths"),
    ]
    for name, desc, source in risk_models:
        with st.expander(f"**{name}**"):
            st.markdown(f"*{desc}*")
            st.caption(f"Source: {source}")
            st.info("Pre-computed value will display here after notebook 05 completes.")
