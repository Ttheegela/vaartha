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
from src.models.regime import get_current_regime, get_regime_stats, get_regime_conditional_returns, get_quant_risk_metrics
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
    st.caption("Six risk models — computed from 2010–2024 Crisis/Normal regime labels")

    risk = get_quant_risk_metrics(demo_mode)

    if not risk:
        st.warning("Risk metrics unavailable — check data loading.")
    else:
        # 1. Bayesian Regime Posterior
        with st.expander("**Bayesian Regime Posterior**  ·  P(Crisis) rolling 30-day mean"):
            st.caption("Rolling 30-day mean of HMM crisis probability — tracks how sustained each regime episode is.")
            rp = risk.get("rolling_posterior", pl.DataFrame())
            if not rp.is_empty():
                current_post = float(rp["rolling_prob"].tail(1)[0])
                st.metric("Current 30-day Posterior P(Crisis)", f"{current_post:.1%}")
                fig_rp = go.Figure(go.Scatter(
                    x=rp["date"].to_list(), y=rp["rolling_prob"].to_list(),
                    line=dict(color="#EF4444", width=1.5), fill="tozeroy",
                    fillcolor="rgba(239,68,68,0.1)",
                ))
                fig_rp.add_hline(y=0.5, line_dash="dash", line_color="#94A3B8")
                fig_rp = set_dark_theme(fig_rp)
                fig_rp.update_layout(height=220, margin=dict(t=10, b=30),
                                     yaxis=dict(range=[0, 1], title="P(Crisis)"),
                                     xaxis_title="Date")
                st.plotly_chart(fig_rp, use_container_width=True)

        # 2. Edge Ratio
        with st.expander("**Edge Ratio**  ·  |Crisis mean return| / |Normal mean return|"):
            st.caption("Values > 1 mean crisis amplifies price moves — higher edge for regime-aware positioning.")
            er = risk.get("edge_ratio", pl.DataFrame())
            if not er.is_empty():
                fig_er = go.Figure(go.Bar(
                    x=er["ticker"].to_list(),
                    y=er["edge_ratio"].to_list(),
                    marker_color=["#EF4444" if v > 1 else "#22C55E" for v in er["edge_ratio"].to_list()],
                ))
                fig_er.add_hline(y=1.0, line_dash="dash", line_color="#94A3B8",
                                 annotation_text="Edge = 1 (no amplification)")
                fig_er = set_dark_theme(fig_er)
                fig_er.update_layout(height=260, margin=dict(t=10, b=30),
                                     xaxis_title="Ticker", yaxis_title="Edge Ratio")
                st.plotly_chart(fig_er, use_container_width=True)

        # 3. Bid-Ask Spread Proxy
        with st.expander("**Bid-Ask Spread Proxy**  ·  Return volatility ratio Crisis/Normal"):
            st.caption("Crisis vol / Normal vol per asset — proxies for liquidity stress and wider spreads during crises.")
            vr = risk.get("vol_ratio", pl.DataFrame())
            if not vr.is_empty():
                fig_vr = go.Figure(go.Bar(
                    x=vr["ticker"].to_list(),
                    y=vr["vol_ratio"].to_list(),
                    marker_color="#F59E0B",
                ))
                fig_vr.add_hline(y=1.0, line_dash="dash", line_color="#94A3B8",
                                 annotation_text="Ratio = 1 (no spread stress)")
                fig_vr = set_dark_theme(fig_vr)
                fig_vr.update_layout(height=260, margin=dict(t=10, b=30),
                                     xaxis_title="Ticker", yaxis_title="Vol Ratio (Crisis/Normal)")
                st.plotly_chart(fig_vr, use_container_width=True)

        # 4. Stoikov Inventory Risk
        with st.expander("**Stoikov Inventory Risk**  ·  Annualized vol × crisis frequency"):
            st.caption("Annualized volatility scaled by the fraction of time spent in crisis — inventory risk proxy for a regime-aware market maker.")
            sv = risk.get("stoikov", pl.DataFrame())
            if not sv.is_empty():
                fig_sv = go.Figure(go.Bar(
                    x=sv["ticker"].to_list(),
                    y=(sv["stoikov_score"] * 100).to_list(),
                    marker_color="#8B5CF6",
                ))
                fig_sv = set_dark_theme(fig_sv)
                fig_sv.update_layout(height=260, margin=dict(t=10, b=30),
                                     xaxis_title="Ticker", yaxis_title="Stoikov Score (%)")
                st.plotly_chart(fig_sv, use_container_width=True)

        # 5. Kelly Criterion
        with st.expander("**Kelly Criterion**  ·  Optimal bet fraction in crisis regime"):
            st.caption("f* = (p·b − (1−p)) / b, where p = P(positive return | Crisis) and b = mean win / mean loss. Negative = fade the move.")
            kl = risk.get("kelly", pl.DataFrame())
            if not kl.is_empty():
                colors = ["#22C55E" if v > 0 else "#EF4444" for v in kl["kelly_f"].to_list()]
                fig_kl = go.Figure(go.Bar(
                    x=kl["ticker"].to_list(),
                    y=kl["kelly_f"].to_list(),
                    marker_color=colors,
                ))
                fig_kl.add_hline(y=0, line_dash="dash", line_color="#94A3B8")
                fig_kl = set_dark_theme(fig_kl)
                fig_kl.update_layout(height=260, margin=dict(t=10, b=30),
                                     xaxis_title="Ticker", yaxis_title="Kelly f*")
                st.plotly_chart(fig_kl, use_container_width=True)

        # 6. Historical VaR 95%
        with st.expander("**Historical VaR 95%**  ·  5th-percentile daily return, Crisis vs Normal"):
            st.caption("Regime-stratified 1-day 95% Value-at-Risk from historical distribution (no parametric assumptions).")
            vv = risk.get("var_95", pl.DataFrame())
            if not vv.is_empty():
                fig_vv = go.Figure()
                fig_vv.add_trace(go.Bar(
                    name="Crisis VaR 95%",
                    x=vv["ticker"].to_list(),
                    y=(vv["var_95_crisis"] * 100).to_list(),
                    marker_color="#EF4444",
                ))
                fig_vv.add_trace(go.Bar(
                    name="Normal VaR 95%",
                    x=vv["ticker"].to_list(),
                    y=(vv["var_95_normal"] * 100).to_list(),
                    marker_color="#22C55E",
                ))
                fig_vv = set_dark_theme(fig_vv)
                fig_vv.update_layout(height=300, barmode="group", margin=dict(t=10, b=30),
                                     xaxis_title="Ticker", yaxis_title="1-Day Return at VaR (%)",
                                     legend=dict(orientation="h", yanchor="bottom", y=1.02))
                st.plotly_chart(fig_vv, use_container_width=True)
