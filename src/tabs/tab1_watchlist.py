"""
tab1_watchlist.py — Portfolio Watchlist
Shows 2010-2024 prices, current regime label, and GeoRisk Score (0-100) for all 12 assets.
Display code only — all data access goes through loaders.py.
"""

import polars as pl
import plotly.graph_objects as go
import streamlit as st
from src.data.loaders import load_prices, load_fred, load_regimes
from src.models.regime import get_current_regime
from src.utils import set_dark_theme, annotate_events, georisk_score
from config import ASSETS, TICKERS, TEAM_PALETTE, DATE_TRAIN_START, KEY_EVENTS


def render(demo_mode: bool = True) -> None:
    """Render the Portfolio Watchlist tab."""
    st.subheader("Portfolio Watchlist")
    st.caption("12-asset geopolitical risk portfolio · 2010–2024 · historically validated")

    prices  = load_prices(demo_mode)
    fred    = load_fred(demo_mode)
    regimes = load_regimes(demo_mode)

    if prices.is_empty():
        st.warning("No price data available. Run `scripts/build_demo_bundle.py` to generate demo data.")
        return

    # ── Current regime banner ─────────────────────────────────────────────────
    regime_info = get_current_regime(demo_mode)
    regime_color = "#EF4444" if regime_info["label"] == "Crisis" else "#22C55E"
    st.markdown(
        f"<div style='background:{regime_color}22;border-left:4px solid {regime_color};"
        f"padding:8px 16px;border-radius:4px;margin-bottom:12px'>"
        f"<b style='color:{regime_color}'>Regime: {regime_info['label']}</b>"
        f" &nbsp;·&nbsp; Crisis prob: {regime_info['prob']:.0%}"
        f" &nbsp;·&nbsp; as of {regime_info['date']}</div>",
        unsafe_allow_html=True,
    )

    # ── GeoRisk Score from GPR ────────────────────────────────────────────────
    georisk = None
    if not fred.is_empty() and "series_id" in fred.columns:
        gpr_df = fred.filter(pl.col("series_id") == "GPR").sort("date")
        if not gpr_df.is_empty():
            gpr_vals = gpr_df["value"].drop_nulls()
            gpr_min  = float(gpr_vals.min())
            gpr_max  = float(gpr_vals.max())
            gpr_last = float(gpr_df["value"][-1])
            georisk  = georisk_score(gpr_last, gpr_min, gpr_max)

    # ── Asset metrics table ────────────────────────────────────────────────────
    st.markdown("### Asset Overview")
    rows = []
    for tkr in TICKERS:
        t = prices.filter(pl.col("ticker") == tkr).sort("date")
        if t.is_empty():
            continue
        close_last  = float(t["close"][-1])
        ret_1d      = float(t["return_1d"][-1]) if "return_1d" in t.columns else 0.0
        # 1-month return (approx 21 trading days)
        ret_1m = (
            (close_last / float(t["close"][-22]) - 1) * 100
            if len(t) >= 22 else None
        )
        rows.append({
            "Ticker":   tkr,
            "Name":     ASSETS[tkr]["name"],
            "Category": ASSETS[tkr]["category"],
            "Price":    f"${close_last:.2f}",
            "1D%":      f"{ret_1d * 100:+.2f}%",
            "1M%":      f"{ret_1m:+.1f}%" if ret_1m is not None else "—",
            "GeoRisk":  f"{georisk:.0f}" if georisk is not None else "—",
        })

    if rows:
        table_df = pl.DataFrame(rows)
        st.dataframe(table_df, use_container_width=True, hide_index=True)

    # ── Normalized price chart ─────────────────────────────────────────────────
    st.markdown("### Normalized Price Index (rebased to 100 at 2010-08-01)")

    fig = go.Figure()

    for tkr in TICKERS:
        t = prices.filter(pl.col("ticker") == tkr).sort("date")
        if t.is_empty() or len(t) < 2:
            continue
        closes    = t["close"].to_list()
        dates     = t["date"].to_list()
        base      = closes[0] if closes[0] != 0 else 1.0
        norm      = [c / base * 100 for c in closes]
        category  = ASSETS[tkr]["category"]
        color     = next(
            (v for k, v in TEAM_PALETTE.items() if k in category),
            "#94A3B8",
        )
        fig.add_trace(go.Scatter(
            x=dates, y=norm,
            name=tkr,
            line=dict(width=1.5, color=color),
            hovertemplate=f"<b>{tkr}</b><br>%{{x}}<br>Index: %{{y:.1f}}<extra></extra>",
        ))

    # Regime shading
    if not regimes.is_empty():
        reg = regimes.sort("date")
        dates_r  = reg["date"].to_list()
        labels_r = reg["regime_label"].to_list()
        start = None
        for i, (d, lbl) in enumerate(zip(dates_r, labels_r)):
            if lbl == "Crisis" and start is None:
                start = d
            elif lbl != "Crisis" and start is not None:
                fig.add_vrect(
                    x0=start, x1=d,
                    fillcolor="#EF4444", opacity=0.08,
                    layer="below", line_width=0,
                )
                start = None
        if start is not None:
            fig.add_vrect(
                x0=start, x1=dates_r[-1],
                fillcolor="#EF4444", opacity=0.08,
                layer="below", line_width=0,
            )

    fig = set_dark_theme(fig)
    fig = annotate_events(fig)
    fig.update_layout(
        height=480,
        xaxis_title="Date",
        yaxis_title="Index (100 = 2010-08-01)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── GPR time series ────────────────────────────────────────────────────────
    if not fred.is_empty() and "series_id" in fred.columns:
        gpr_df = fred.filter(pl.col("series_id") == "GPR").sort("date")
        if not gpr_df.is_empty():
            st.markdown("### Geopolitical Risk Index (GPR)")
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=gpr_df["date"].to_list(),
                y=gpr_df["value"].to_list(),
                name="GPR",
                line=dict(color="#FACC15", width=2),
                fill="tozeroy",
                fillcolor="rgba(250,204,21,0.08)",
            ))
            fig2 = set_dark_theme(fig2)
            fig2 = annotate_events(fig2)
            fig2.update_layout(
                height=300,
                xaxis_title="Date",
                yaxis_title="GPR Index",
                hovermode="x unified",
            )
            st.plotly_chart(fig2, use_container_width=True)
