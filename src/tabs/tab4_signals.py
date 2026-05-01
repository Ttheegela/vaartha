"""
tab4_signals.py — Return Signals
XGBoost walk-forward predictions + Kronos forecasts + backtest charts.
OOS metrics only — never display in-sample accuracy.
Display code only — all data access goes through loaders.py.
"""

import polars as pl
import plotly.graph_objects as go
import streamlit as st
from src.data.loaders import load_prices, load_regimes
from src.models.signals import load_oos_metrics, get_all_tickers_oos_summary, get_ticker_oos_summary
from src.models.kronos import get_ticker_forecast, get_forecast_summary
from src.utils import set_dark_theme, annotate_events
from config import TICKERS, ASSETS


def render(demo_mode: bool = True) -> None:
    """Render the Return Signals tab."""
    st.subheader("Return Signals")
    st.caption("XGBoost walk-forward OOS · Kronos zero-shot 21-day forecasts · no in-sample metrics")

    prices  = load_prices(demo_mode)
    regimes = load_regimes(demo_mode)

    if prices.is_empty():
        st.warning("No price data available.")
        return

    # ── OOS summary table — all tickers ───────────────────────────────────────
    st.markdown("### XGBoost Walk-Forward OOS — All Assets")
    oos_summary = get_all_tickers_oos_summary(demo_mode)
    if not oos_summary.is_empty():
        st.dataframe(
            oos_summary.rename({
                "ticker":         "Ticker",
                "mean_accuracy":  "OOS Accuracy",
                "mean_precision": "OOS Precision",
                "mean_recall":    "OOS Recall",
                "n_folds":        "Folds",
            }),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("OOS metrics not available yet — run notebooks/05_signals.ipynb first.")

    st.divider()

    # ── Per-ticker deep dive ──────────────────────────────────────────────────
    ticker = st.selectbox("Select asset for deep dive", TICKERS, format_func=lambda t: f"{t} — {ASSETS[t]['name']}")

    col1, col2 = st.columns(2)

    # XGBoost OOS for selected ticker
    with col1:
        st.markdown(f"#### {ticker} — XGBoost OOS Folds")
        oos_df = load_oos_metrics(demo_mode)
        if not oos_df.is_empty():
            t_oos = oos_df.filter(pl.col("ticker") == ticker).sort("test_start")
            if not t_oos.is_empty():
                summary = get_ticker_oos_summary(ticker, demo_mode)
                st.metric("Mean OOS Accuracy", f"{summary.get('mean_accuracy', 0):.1%}")
                st.metric("Mean OOS Precision", f"{summary.get('mean_precision', 0):.1%}")
                st.metric("Mean OOS Recall",    f"{summary.get('mean_recall', 0):.1%}")

                # Per-fold accuracy bar chart
                fig = go.Figure(go.Bar(
                    x=[str(r) for r in t_oos["test_start"].to_list()],
                    y=t_oos["oos_accuracy"].to_list(),
                    marker_color=[
                        "#22C55E" if v >= 0.55 else "#EF4444"
                        for v in t_oos["oos_accuracy"].to_list()
                    ],
                    hovertemplate="Fold start: %{x}<br>OOS Accuracy: %{y:.1%}<extra></extra>",
                ))
                fig.add_hline(y=0.5, line_dash="dash", line_color="#94A3B8", annotation_text="50% baseline")
                fig = set_dark_theme(fig)
                fig.update_layout(
                    height=260,
                    xaxis_title="Test Start Date",
                    yaxis_title="OOS Accuracy",
                    yaxis=dict(tickformat=".0%"),
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(f"No OOS folds for {ticker}.")
        else:
            st.info("Run notebooks/05_signals.ipynb to generate OOS metrics.")

    # Kronos forecast for selected ticker
    with col2:
        st.markdown(f"#### {ticker} — Kronos 21-Day Forecast")
        forecast = get_ticker_forecast(ticker, demo_mode)
        price_t  = prices.filter(pl.col("ticker") == ticker).sort("date")

        if not forecast.is_empty():
            last_close = float(forecast["last_close"][0])
            end_mean   = float(forecast["mean"][-1])
            exp_ret    = (end_mean / last_close - 1) * 100 if last_close > 0 else 0.0

            st.metric("Last Close",      f"${last_close:.2f}")
            st.metric("21-Day Forecast", f"${end_mean:.2f}", delta=f"{exp_ret:+.1f}%")

            fig2 = go.Figure()

            # Historical (last 60 days)
            if not price_t.is_empty():
                hist = price_t.tail(60)
                fig2.add_trace(go.Scatter(
                    x=hist["date"].to_list(),
                    y=hist["close"].to_list(),
                    name="Historical",
                    line=dict(color="#94A3B8", width=1.5),
                ))

            # 80% CI band
            fig2.add_trace(go.Scatter(
                x=forecast["forecast_date"].to_list() + forecast["forecast_date"].to_list()[::-1],
                y=forecast["high_80"].to_list() + forecast["low_80"].to_list()[::-1],
                fill="toself",
                fillcolor="rgba(255,107,53,0.15)",
                line=dict(color="rgba(0,0,0,0)"),
                name="80% CI",
                showlegend=True,
            ))

            # Forecast mean
            fig2.add_trace(go.Scatter(
                x=forecast["forecast_date"].to_list(),
                y=forecast["mean"].to_list(),
                name="Kronos Mean",
                line=dict(color="#FF6B35", width=2),
            ))

            fig2 = set_dark_theme(fig2)
            fig2.update_layout(
                height=320,
                xaxis_title="Date",
                yaxis_title=f"{ticker} Price ($)",
                hovermode="x unified",
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Run notebooks/07_kronos_forecasts.ipynb to generate forecasts.")

    # ── Kronos summary — all tickers ──────────────────────────────────────────
    st.divider()
    st.markdown("### Kronos 21-Day Expected Returns — All Assets")
    kron_summary = get_forecast_summary(demo_mode)
    if not kron_summary.is_empty():
        fig3 = go.Figure(go.Bar(
            x=kron_summary["ticker"].to_list(),
            y=kron_summary["expected_return_pct"].to_list(),
            marker_color=[
                "#22C55E" if v >= 0 else "#EF4444"
                for v in kron_summary["expected_return_pct"].to_list()
            ],
            hovertemplate="%{x}<br>Expected: %{y:.2f}%<extra></extra>",
        ))
        fig3.add_hline(y=0, line_color="#475569", line_width=1)
        fig3 = set_dark_theme(fig3)
        fig3.update_layout(
            height=320,
            xaxis_title="Ticker",
            yaxis_title="21-Day Expected Return (%)",
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("Kronos forecasts not available yet.")
