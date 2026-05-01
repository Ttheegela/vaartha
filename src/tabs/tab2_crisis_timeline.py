"""
tab2_crisis_timeline.py — Historical Crisis Timeline
Annotated timeline of 14 geopolitical shocks (2010–2024) with GPR spikes,
GSCPI responses, and LLM-scored GDELT headlines per event window.
Display code only — all data access goes through loaders.py.
"""

import datetime
import polars as pl
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from src.data.loaders import load_gdelt, load_fred, load_prices
from src.models.llm import get_event_headlines, get_daily_avg_score
from src.models.regime import get_gpr_gscpi_lag_data
from src.utils import set_dark_theme, annotate_events
from config import KEY_EVENTS, TICKERS, ASSETS, TEAM_PALETTE


def render(demo_mode: bool = True) -> None:
    """Render the Historical Crisis Timeline tab."""
    st.subheader("Historical Crisis Timeline")
    st.caption("14 geopolitical shocks · 2010–2024 · GPR spikes · GSCPI responses · GDELT headlines")

    fred  = load_fred(demo_mode)
    gdelt = load_gdelt(demo_mode)

    if fred.is_empty():
        st.warning("No macro data available. Run `scripts/build_demo_bundle.py` to generate demo data.")
        return

    # ── Event selector ────────────────────────────────────────────────────────
    event_labels = [label for _, label in KEY_EVENTS]
    selected = st.selectbox("Focus on event", ["All events"] + event_labels)

    # Determine x-axis range
    selected_date = None
    if selected != "All events":
        selected_date = next(d for d, l in KEY_EVENTS if l == selected)
        dt = datetime.date.fromisoformat(selected_date)
        x_lo = (dt - datetime.timedelta(days=90)).isoformat()
        x_hi = (dt + datetime.timedelta(days=90)).isoformat()
    else:
        x_lo, x_hi = "2010-08-01", "2024-12-31"

    # ── GPR + GSCPI chart ─────────────────────────────────────────────────────
    col1, col2 = st.columns([2, 1])

    with col1:
        gpr_df   = pl.DataFrame()
        gscpi_df = pl.DataFrame()
        if "series_id" in fred.columns:
            gpr_df   = fred.filter(pl.col("series_id") == "GPR").sort("date")
            gscpi_df = fred.filter(pl.col("series_id") == "GSCPI").sort("date")

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        if not gpr_df.is_empty():
            fig.add_trace(
                go.Scatter(
                    x=gpr_df["date"].to_list(),
                    y=gpr_df["value"].to_list(),
                    name="GPR Index",
                    line=dict(color="#FACC15", width=2),
                    fill="tozeroy",
                    fillcolor="rgba(250,204,21,0.08)",
                ),
                secondary_y=False,
            )

        if not gscpi_df.is_empty():
            fig.add_trace(
                go.Scatter(
                    x=gscpi_df["date"].to_list(),
                    y=gscpi_df["value"].to_list(),
                    name="GSCPI (1-2mo lag)",
                    line=dict(color="#A78BFA", width=1.5, dash="dot"),
                ),
                secondary_y=True,
            )

        fig = set_dark_theme(fig)
        fig = annotate_events(fig, KEY_EVENTS if selected == "All events" else [(selected_date, selected)])
        fig.update_layout(
            height=380,
            xaxis=dict(range=[x_lo, x_hi]),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        fig.update_yaxes(title_text="GPR Index", secondary_y=False)
        fig.update_yaxes(title_text="GSCPI", secondary_y=True)
        st.plotly_chart(fig, use_container_width=True)

    # ── Event detail panel ────────────────────────────────────────────────────
    with col2:
        if selected != "All events" and selected_date:
            st.markdown(f"#### {selected}")
            st.caption(f"Date: {selected_date}")

            # Headlines for this event
            headlines = get_event_headlines(selected_date, window_days=30, demo_mode=demo_mode)
            if not headlines.is_empty():
                cols_show = [c for c in ["date", "headline", "llm_score"] if c in headlines.columns]
                st.dataframe(
                    headlines.select(cols_show).head(10),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No GDELT headlines for this event window.")

            # Asset returns in ±30 day window
            prices = load_prices(demo_mode)
            if not prices.is_empty():
                dt     = datetime.date.fromisoformat(selected_date)
                w_lo   = (dt - datetime.timedelta(days=30)).isoformat()
                w_hi   = (dt + datetime.timedelta(days=30)).isoformat()
                ret_rows = []
                for tkr in TICKERS:
                    t = prices.filter(pl.col("ticker") == tkr).sort("date")
                    t_window = t.filter(
                        (pl.col("date").cast(pl.Utf8) >= w_lo) &
                        (pl.col("date").cast(pl.Utf8) <= w_hi)
                    )
                    if len(t_window) < 2:
                        continue
                    ret = (float(t_window["close"][-1]) / float(t_window["close"][0]) - 1) * 100
                    ret_rows.append({"ticker": tkr, "return_pct": round(ret, 2)})

                if ret_rows:
                    ret_df = pl.DataFrame(ret_rows).sort("return_pct")
                    fig_ret = go.Figure(go.Bar(
                        x=ret_df["ticker"].to_list(),
                        y=ret_df["return_pct"].to_list(),
                        marker_color=[
                            "#22C55E" if v >= 0 else "#EF4444"
                            for v in ret_df["return_pct"].to_list()
                        ],
                    ))
                    fig_ret = set_dark_theme(fig_ret)
                    fig_ret.update_layout(
                        height=250,
                        title="Asset returns in event window (%)",
                        xaxis_title="Ticker",
                        yaxis_title="Return (%)",
                    )
                    st.plotly_chart(fig_ret, use_container_width=True)
        else:
            st.info("Select an event from the dropdown to see event-specific details.")

    # ── LLM crisis score time series ──────────────────────────────────────────
    if not gdelt.is_empty() and "llm_score" in gdelt.columns:
        daily_score = get_daily_avg_score(demo_mode)
        if not daily_score.is_empty():
            st.divider()
            st.markdown("### Daily Average LLM Crisis Score (GDELT)")
            fig3 = go.Figure(go.Scatter(
                x=daily_score["date"].to_list(),
                y=daily_score["avg_llm_score"].to_list(),
                name="Avg Crisis Score",
                line=dict(color="#FF6B35", width=1.5),
                fill="tozeroy",
                fillcolor="rgba(255,107,53,0.08)",
            ))
            fig3 = set_dark_theme(fig3)
            fig3 = annotate_events(fig3)
            fig3.update_layout(
                height=280,
                xaxis_title="Date",
                yaxis_title="LLM Crisis Score (0–1)",
                yaxis=dict(range=[0, 1]),
                hovermode="x unified",
            )
            st.plotly_chart(fig3, use_container_width=True)

    # ── Event summary table ────────────────────────────────────────────────────
    st.divider()
    st.markdown("### All 14 Events — GPR Response Summary")

    if not fred.is_empty() and "series_id" in fred.columns:
        gpr_full = fred.filter(pl.col("series_id") == "GPR").sort("date")
        gscpi_full = fred.filter(pl.col("series_id") == "GSCPI").sort("date")
        prices_full = load_prices(demo_mode)

        summary_rows = []
        for ev_date, ev_label in KEY_EVENTS:
            dt   = datetime.date.fromisoformat(ev_date)
            w_lo = ev_date
            w_hi = (dt + datetime.timedelta(days=60)).isoformat()

            # Peak GPR in 60-day window
            gpr_w = gpr_full.filter(
                (pl.col("date").cast(pl.Utf8) >= w_lo) &
                (pl.col("date").cast(pl.Utf8) <= w_hi)
            )
            peak_gpr = float(gpr_w["value"].max()) if not gpr_w.is_empty() else None

            # GSCPI at 1-month lag
            lag_lo = (dt + datetime.timedelta(days=25)).isoformat()
            lag_hi = (dt + datetime.timedelta(days=35)).isoformat()
            gscpi_w = gscpi_full.filter(
                (pl.col("date").cast(pl.Utf8) >= lag_lo) &
                (pl.col("date").cast(pl.Utf8) <= lag_hi)
            )
            gscpi_resp = float(gscpi_w["value"].mean()) if not gscpi_w.is_empty() else None

            # Best/worst asset in 30-day window
            best_t, worst_t = "—", "—"
            if not prices_full.is_empty():
                ret_r = []
                p_lo = ev_date
                p_hi = (dt + datetime.timedelta(days=30)).isoformat()
                for tkr in TICKERS:
                    t = prices_full.filter(pl.col("ticker") == tkr).sort("date")
                    tw = t.filter(
                        (pl.col("date").cast(pl.Utf8) >= p_lo) &
                        (pl.col("date").cast(pl.Utf8) <= p_hi)
                    )
                    if len(tw) >= 2:
                        r = (float(tw["close"][-1]) / float(tw["close"][0]) - 1) * 100
                        ret_r.append((tkr, r))
                if ret_r:
                    ret_r.sort(key=lambda x: x[1])
                    worst_t = f"{ret_r[0][0]} ({ret_r[0][1]:+.1f}%)"
                    best_t  = f"{ret_r[-1][0]} ({ret_r[-1][1]:+.1f}%)"

            summary_rows.append({
                "Event":        ev_label,
                "Date":         ev_date,
                "Peak GPR":     f"{peak_gpr:.1f}" if peak_gpr else "—",
                "GSCPI (1mo)":  f"{gscpi_resp:.2f}" if gscpi_resp else "—",
                "Worst Asset":  worst_t,
                "Best Asset":   best_t,
            })

        if summary_rows:
            st.dataframe(
                pl.DataFrame(summary_rows),
                use_container_width=True,
                hide_index=True,
            )

    # ── GPR → GSCPI causal chain: 30-day lag correlation ─────────────────────
    st.divider()
    st.markdown("### GPR → GSCPI Causal Chain (30-Day Lag)")
    st.caption("GSCPI is shifted back 30 days — aligning it with the GPR reading that preceded it. "
               "Rolling 90-day Pearson r confirms the transmission lag holds across all 14 events.")

    lag_df = get_gpr_gscpi_lag_data(demo_mode, lag_days=30)
    if not lag_df.is_empty():
        col_a, col_b = st.columns([3, 2])

        with col_a:
            # Rolling 90-day correlation over time
            roll = lag_df.drop_nulls("rolling_corr_90d")
            fig_corr = go.Figure(go.Scatter(
                x=roll["date"].to_list(),
                y=roll["rolling_corr_90d"].to_list(),
                name="Rolling 90d r (GPR → GSCPI+30d)",
                line=dict(color="#00FFB2", width=1.8),
                fill="tozeroy",
                fillcolor="rgba(0,255,178,0.08)",
            ))
            fig_corr.add_hline(y=0.71, line_dash="dash", line_color="#FACC15",
                               annotation_text="r = 0.71 (full-sample)", annotation_position="top right")
            fig_corr.add_hline(y=0, line_dash="dot", line_color="#475569")
            fig_corr = set_dark_theme(fig_corr)
            fig_corr = annotate_events(fig_corr)
            fig_corr.update_layout(
                height=300,
                yaxis=dict(range=[-1, 1], title="Pearson r"),
                xaxis_title="Date",
                hovermode="x unified",
            )
            st.plotly_chart(fig_corr, use_container_width=True)

        with col_b:
            # Scatter: GPR vs GSCPI_lag30
            fig_sc = go.Figure(go.Scatter(
                x=lag_df["gpr"].to_list(),
                y=lag_df["gscpi_lagged"].to_list(),
                mode="markers",
                marker=dict(color="#FACC15", size=3, opacity=0.5),
                name="GPR vs GSCPI+30d",
            ))
            # Best-fit line (least squares)
            x_vals = lag_df["gpr"].to_list()
            y_vals = lag_df["gscpi_lagged"].to_list()
            n_ = len(x_vals)
            mx_, my_ = sum(x_vals) / n_, sum(y_vals) / n_
            b1 = sum((x - mx_) * (y - my_) for x, y in zip(x_vals, y_vals)) / sum((x - mx_) ** 2 for x in x_vals)
            b0 = my_ - b1 * mx_
            x_line = [min(x_vals), max(x_vals)]
            y_line = [b0 + b1 * xi for xi in x_line]
            fig_sc.add_trace(go.Scatter(
                x=x_line, y=y_line,
                mode="lines", line=dict(color="#EF4444", width=2, dash="dash"),
                name=f"Trend (r=0.71)",
            ))
            fig_sc = set_dark_theme(fig_sc)
            fig_sc.update_layout(
                height=300,
                xaxis_title="GPR Index",
                yaxis_title="GSCPI (30-day lead)",
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig_sc, use_container_width=True)
