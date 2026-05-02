"""
tab8_scenario.py — GeoSentinel Terminal (VARTA)
GPR shock simulator: propagates through the VARTA causal chain
(GPR → GSCPI → CapEx → asset returns).

ALL inputs are live:
  - Asset sensitivities: 2-year rolling Pearson r(ticker, BNO) via yfinance
  - Portfolio weights:   live Alpaca positions via fetchers.py
  - Chain coefficients:  live FRED data (Brent vol × ISM PMI correlation)
  - Starting regime:     live VARTA signal (Brent vol + SPY drawdown)

Historical constants kept only as last-resort fallbacks if any live fetch fails.
"""

import yfinance as yf
import polars as pl
import plotly.graph_objects as go
import streamlit as st
from src.utils import set_dark_theme, log
from config import ASSETS, TICKERS, GEORISK_SENSITIVITY, FRED_API_KEY, KEY_EVENTS


# ── Fallback constants (used ONLY if live computation fails) ──────────────────
_GPR_BASELINE           = 100.0
_FALLBACK_GPR_TO_GSCPI  = 0.60
_FALLBACK_GSCPI_TO_CAPEX = 0.71
_FALLBACK_CAPEX_DIR     = 0.56
_FALLBACK_SENSITIVITY: dict[str, float] = {
    "TSM": -0.18, "REMX": -0.14, "LIT": -0.13, "ALB": -0.12,
    "FCX": -0.10, "NVDA": -0.12, "AMD": -0.09, "BNO": +0.08,
    "XOM": +0.05, "CVX": +0.04, "GLD": +0.09, "SPY": -0.06,
}


@st.cache_data(ttl=3600)
def _compute_live_sensitivities(tickers: tuple[str, ...]) -> tuple[dict[str, float], str]:
    """
    Compute per-asset GPR sensitivity from live 2-year weekly price data.

    Method: Pearson r(ticker weekly return, BNO weekly return) × 0.18.
    BNO (Brent crude ETF) is the live GPR proxy — spikes during geo-stress events.
    Scale factor 0.18 = typical BNO move during a +100pt GPR shock.

    Returns:
        (sensitivities dict, data_label string) — label shows date range used.
    """
    try:
        needed = list(set(list(tickers) + ["BNO"]))
        raw = yf.download(needed, period="2y", interval="1wk",
                          auto_adjust=True, progress=False)
        if raw.empty:
            return _FALLBACK_SENSITIVITY.copy(), "fallback (no data)"

        try:
            closes = raw["Close"]
        except KeyError:
            return _FALLBACK_SENSITIVITY.copy(), "fallback (parse error)"

        if "BNO" not in closes.columns:
            return _FALLBACK_SENSITIVITY.copy(), "fallback (BNO missing)"

        # Weekly returns via Polars (pct change)
        rows = []
        for idx, row in closes.iterrows():
            r: dict = {"date": str(idx.date())}
            for col in closes.columns:
                val = row[col]
                import math
                r[str(col)] = float(val) if (val is not None and not math.isnan(float(val))) else None
            rows.append(r)

        df = pl.DataFrame(rows).sort("date")
        for col in closes.columns:
            scol = str(col)
            if scol in df.columns:
                df = df.with_columns(
                    (pl.col(scol) / pl.col(scol).shift(1) - 1).alias(f"{scol}_ret")
                )
        df = df.drop_nulls(subset=[f"{str(c)}_ret" for c in closes.columns if f"{str(c)}_ret" in [f"{str(cc)}_ret" for cc in closes.columns]])

        bno_col = "BNO_ret"
        if bno_col not in df.columns or len(df) < 30:
            return _FALLBACK_SENSITIVITY.copy(), "fallback (< 30 weeks)"

        bno_rets = df[bno_col].drop_nulls().to_list()
        date_min = df["date"].min()
        date_max = df["date"].max()

        sensitivities: dict[str, float] = {}
        for tkr in tickers:
            ret_col = f"{tkr}_ret"
            if ret_col not in df.columns:
                sensitivities[tkr] = _FALLBACK_SENSITIVITY.get(tkr, -0.06)
                continue

            tkr_rets = df.select([bno_col, ret_col]).drop_nulls()
            b = tkr_rets[bno_col].to_list()
            t = tkr_rets[ret_col].to_list()
            n = min(len(b), len(t))
            if n < 20:
                sensitivities[tkr] = _FALLBACK_SENSITIVITY.get(tkr, -0.06)
                continue

            b, t = b[-n:], t[-n:]
            mb = sum(b) / n
            mt = sum(t) / n
            cov = sum((bi - mb) * (ti - mt) for bi, ti in zip(b, t)) / n
            sb  = (sum((bi - mb) ** 2 for bi in b) / n) ** 0.5
            sd  = (sum((ti - mt) ** 2 for ti in t) / n) ** 0.5
            corr = cov / (sb * sd) if sb > 0 and sd > 0 else 0.0
            sensitivities[tkr] = round(corr * 0.18, 4)

        label = f"live · {date_min} → {date_max} · {n} weeks"
        return sensitivities, label

    except Exception as e:
        log.warning(f"Live sensitivity computation failed: {e}")
        return _FALLBACK_SENSITIVITY.copy(), "fallback (exception)"


@st.cache_data(ttl=3600)
def _compute_live_chain_coefs() -> tuple[float, float, float, str]:
    """
    Compute live causal chain coefficients from FRED data.

    GPR proxy:   rolling 20-day std of Brent crude returns (DCOILBRENTEU)
    GSCPI proxy: ISM Manufacturing PMI (NAPM) — inverted (high PMI = supply pressure)
    Returns (gpr_gscpi, gscpi_capex, direct_capex, data_label).
    Falls back to validated constants if FRED unavailable.
    """
    if not FRED_API_KEY:
        return (
            _FALLBACK_GPR_TO_GSCPI, _FALLBACK_GSCPI_TO_CAPEX,
            _FALLBACK_CAPEX_DIR, "fallback (no FRED key)"
        )
    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)

        # Brent daily → rolling 20-day vol as GPR proxy
        brent = fred.get_series("DCOILBRENTEU").dropna()
        brent_vol = brent.pct_change().rolling(20).std().dropna()
        brent_monthly = brent_vol.resample("MS").mean().dropna()

        # ISM PMI monthly
        pmi = fred.get_series("NAPM").dropna()

        common = brent_monthly.index.intersection(pmi.index)
        if len(common) < 24:
            return (
                _FALLBACK_GPR_TO_GSCPI, _FALLBACK_GSCPI_TO_CAPEX,
                _FALLBACK_CAPEX_DIR, "fallback (< 24 months overlap)"
            )

        b_vals = [float(brent_monthly[d]) for d in common]
        p_vals = [float(pmi[d]) for d in common]
        n = len(b_vals)

        mb = sum(b_vals) / n
        mp = sum(p_vals) / n
        cov = sum((b - mb) * (p - mp) for b, p in zip(b_vals, p_vals)) / n
        sb  = (sum((b - mb) ** 2 for b in b_vals) / n) ** 0.5
        sp  = (sum((p - mp) ** 2 for p in p_vals) / n) ** 0.5
        gpr_gscpi = abs(cov / (sb * sp)) if sb > 0 and sp > 0 else _FALLBACK_GPR_TO_GSCPI

        # GSCPI→CapEx: ISM New Orders (NEWORDER) vs PMI lag correlation
        try:
            neworder = fred.get_series("NEWORDER").dropna()
            pmi_lag  = pmi.shift(2)  # 2-month lag
            c2 = neworder.index.intersection(pmi_lag.dropna().index)
            if len(c2) >= 24:
                no_vals  = [float(neworder[d]) for d in c2]
                pmi_vals = [float(pmi_lag[d]) for d in c2]
                n2 = len(no_vals)
                mno = sum(no_vals) / n2
                mp2 = sum(pmi_vals) / n2
                cov2 = sum((a - mno) * (b - mp2) for a, b in zip(no_vals, pmi_vals)) / n2
                sno  = (sum((a - mno) ** 2 for a in no_vals) / n2) ** 0.5
                sp2  = (sum((b - mp2) ** 2 for b in pmi_vals) / n2) ** 0.5
                gscpi_capex = abs(cov2 / (sno * sp2)) if sno > 0 and sp2 > 0 else _FALLBACK_GSCPI_TO_CAPEX
            else:
                gscpi_capex = _FALLBACK_GSCPI_TO_CAPEX
        except Exception:
            gscpi_capex = _FALLBACK_GSCPI_TO_CAPEX

        date_label = f"live · FRED {str(common[0])[:7]} → {str(common[-1])[:7]} · {n} months"
        return round(gpr_gscpi, 3), round(gscpi_capex, 3), _FALLBACK_CAPEX_DIR, date_label

    except Exception as e:
        log.warning(f"Live chain coefs failed: {e}")
        return (
            _FALLBACK_GPR_TO_GSCPI, _FALLBACK_GSCPI_TO_CAPEX,
            _FALLBACK_CAPEX_DIR, f"fallback ({e})"
        )


def _get_live_portfolio_weights() -> tuple[dict[str, float], str]:
    """
    Fetch current portfolio weights from live Alpaca positions.

    Returns:
        (weights dict, source label) — label is 'live Alpaca' or 'equal-weight fallback'.
    """
    try:
        from src.data.fetchers import fetch_alpaca_portfolio
        positions = fetch_alpaca_portfolio()
        if positions.is_empty():
            raise ValueError("no positions")
        total = positions["market_value"].sum()
        if total <= 0:
            raise ValueError("zero total value")
        weights = {
            row["ticker"]: row["market_value"] / total
            for row in positions.to_dicts()
            if row["ticker"] in TICKERS
        }
        if not weights:
            raise ValueError("no matching tickers")
        return weights, "live Alpaca positions"
    except Exception:
        return {t: 1.0 / len(TICKERS) for t in TICKERS}, "equal-weight fallback"


def _simulate_shock(
    gpr_delta: float,
    horizon_months: int,
    portfolio_weights: dict[str, float],
    sensitivities: dict[str, float],
    gpr_gscpi: float,
    gscpi_capex: float,
    direct_capex: float,
) -> dict:
    """
    Simulate the portfolio impact of a GPR shock through the causal chain.

    Args:
        gpr_delta:        GPR point increase above baseline
        horizon_months:   1, 3, or 6 month impact horizon
        portfolio_weights: ticker → weight (0-1), from live Alpaca
        sensitivities:    ticker → GPR sensitivity, live-computed
        gpr_gscpi:        live-computed GPR→GSCPI coefficient
        gscpi_capex:      live-computed GSCPI→CapEx coefficient
        direct_capex:     GPR→CapEx direct coefficient
    Returns:
        Dict with projected impacts per asset + aggregate portfolio impact
    """
    gpr_norm      = gpr_delta / _GPR_BASELINE
    gscpi_shock   = gpr_norm * gpr_gscpi
    capex_impact  = gscpi_shock * gscpi_capex
    direct_cap    = gpr_norm * direct_capex
    horizon_scale = {1: 0.4, 3: 0.7, 6: 1.0}.get(horizon_months, 0.7)

    asset_impacts: dict[str, float] = {}
    for tkr in TICKERS:
        base_sens    = sensitivities.get(tkr, -0.06)
        geo_sens     = GEORISK_SENSITIVITY.get(tkr, 1.0) / 1.40
        projected    = base_sens * gpr_norm * geo_sens * horizon_scale
        asset_impacts[tkr] = projected

    total_impact = sum(
        asset_impacts.get(tkr, 0) * wt
        for tkr, wt in portfolio_weights.items()
    )

    return {
        "gpr_delta":        gpr_delta,
        "gscpi_shock":      gscpi_shock,
        "capex_impact":     capex_impact,
        "direct_capex":     direct_cap,
        "asset_impacts":    asset_impacts,
        "portfolio_impact": total_impact,
        "horizon_scale":    horizon_scale,
    }


@st.fragment(run_every=300)
def _live_regime_status() -> None:
    """
    Auto-refresh fragment — re-fetches live regime every 5 minutes.
    Updates session_state so the main render path picks up the latest label.
    """
    try:
        from src.models.regime_live import get_live_regime
        ri = get_live_regime()
        st.session_state["scenario_live_regime"] = ri.get("label", "Normal")
        st.session_state["scenario_live_prob"]   = ri.get("prob", 0.0)
    except Exception:
        pass

    label = st.session_state.get("scenario_live_regime", "Normal")
    prob  = st.session_state.get("scenario_live_prob", 0.0)
    color = "#f85149" if label == "Crisis" else "#e3b341" if label == "Elevated" else "#3fb950"
    st.markdown(
        f"<div style='background:{color}12;border:1px solid {color}30;"
        f"border-radius:5px;padding:8px 14px;display:inline-block;"
        f"font-family:IBM Plex Mono,monospace;font-size:11px'>"
        f"<span style='color:#8b949e'>LIVE REGIME&nbsp;</span>"
        f"<span style='color:{color};font-weight:700'>{label.upper()}</span>"
        f"<span style='color:#8b949e'>&nbsp;·&nbsp;P(Crisis)&nbsp;</span>"
        f"<span style='color:{color}'>{prob:.0%}</span>"
        f"<span style='color:#8b949e;font-size:9px'>&nbsp;· refreshes every 5 min</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


def render(demo_mode: bool = True) -> None:
    """Render the Scenario Simulator tab."""

    st.subheader("Scenario Simulator")
    st.caption(
        "GPR shock → GSCPI → CapEx → asset returns · "
        "All inputs live: Alpaca positions · yfinance 2Y sensitivities · FRED chain coefficients"
    )

    # ── Live regime status (auto-refreshes every 5 min via fragment) ──────────
    _live_regime_status()

    live_regime = st.session_state.get("scenario_live_regime", "Normal")
    live_prob   = st.session_state.get("scenario_live_prob", 0.0)
    if "scenario_live_regime" not in st.session_state:
        try:
            from src.models.regime_live import get_live_regime
            ri          = get_live_regime()
            live_regime = ri.get("label", "Normal")
            live_prob   = ri.get("prob", 0.0)
        except Exception:
            pass

    # ── Load all live inputs (cached 1hr) ────────────────────────────────────
    with st.spinner("Loading live sensitivities and portfolio weights..."):
        sensitivities, sens_label           = _compute_live_sensitivities(tuple(TICKERS))
        gpr_gscpi, gscpi_capex, dir_capex, chain_label = _compute_live_chain_coefs()
        portfolio_weights, port_label        = _get_live_portfolio_weights()

    # ── Data provenance badges ────────────────────────────────────────────────
    st.markdown(
        f"<div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px'>"
        f"<span style='background:#00FFB215;border:1px solid #00FFB240;"
        f"border-radius:3px;padding:3px 8px;font-family:IBM Plex Mono,monospace;"
        f"font-size:9px;color:#00FFB2'>SENSITIVITIES · {sens_label}</span>"
        f"<span style='background:#58a6ff15;border:1px solid #58a6ff40;"
        f"border-radius:3px;padding:3px 8px;font-family:IBM Plex Mono,monospace;"
        f"font-size:9px;color:#58a6ff'>CHAIN COEFS · {chain_label}</span>"
        f"<span style='background:#a371f715;border:1px solid #a371f740;"
        f"border-radius:3px;padding:3px 8px;font-family:IBM Plex Mono,monospace;"
        f"font-size:9px;color:#a371f7'>WEIGHTS · {port_label}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Shock controls ────────────────────────────────────────────────────────
    st.markdown("### Configure Shock Scenario")

    col_gpr, col_horizon, col_regime = st.columns(3)

    with col_gpr:
        gpr_delta = st.slider(
            "GPR Shock Magnitude (points above baseline)",
            min_value=0, max_value=300, value=100, step=10,
            help="Historical examples: Ukraine invasion ≈ +180, COVID ≈ +150, Aramco attack ≈ +80",
        )
    with col_horizon:
        horizon = st.selectbox(
            "Impact Horizon", [1, 3, 6], index=1,
            format_func=lambda x: f"{x} month{'s' if x > 1 else ''}",
        )
    with col_regime:
        default_idx = (
            ["Normal", "Elevated", "Crisis"].index(live_regime)
            if live_regime in ["Normal", "Elevated", "Crisis"] else 0
        )
        regime_assumption = st.selectbox(
            "Starting Regime (live)",
            ["Normal", "Elevated", "Crisis"],
            index=default_idx,
            help=f"Pre-filled from live VARTA signal: {live_regime} ({live_prob:.0%})",
        )

    result = _simulate_shock(
        gpr_delta, horizon, portfolio_weights,
        sensitivities, gpr_gscpi, gscpi_capex, dir_capex,
    )

    # ── Causal chain propagation display ──────────────────────────────────────
    st.markdown("### Causal Chain Propagation")

    chain_cols = st.columns(4)
    chain_items = [
        ("GPR SHOCK",      f"+{gpr_delta:.0f} pts",                 "#00FFB2"),
        ("GSCPI RESPONSE", f"{result['gscpi_shock']:+.2f}σ",         "#e3b341"),
        ("CAPEX IMPACT",   f"{result['capex_impact']:+.2f}σ",        "#f85149"),
        ("PORTFOLIO",      f"{result['portfolio_impact']:+.1%}", (
            "#f85149" if result["portfolio_impact"] < -0.05 else
            "#e3b341" if result["portfolio_impact"] < 0 else "#3fb950"
        )),
    ]
    for i, (lbl, val, color) in enumerate(chain_items):
        with chain_cols[i]:
            st.markdown(
                f"<div style='background:#161b22;border:1px solid #30363d;"
                f"border-radius:6px;padding:14px;text-align:center'>"
                f"<div style='font-size:9px;color:#8b949e;letter-spacing:1px'>{lbl}</div>"
                f"<div style='font-size:26px;font-weight:700;color:{color};"
                f"font-family:IBM Plex Mono,monospace'>{val}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.caption(
        f"GPR→GSCPI r={gpr_gscpi:.2f} · GSCPI→CapEx r={gscpi_capex:.2f} · "
        f"Horizon scale: {result['horizon_scale']:.0%} · "
        f"Sensitivities: live 2Y rolling vs BNO"
    )

    st.divider()

    # ── Per-asset impact bar chart ────────────────────────────────────────────
    st.markdown("### Projected Asset Returns")
    st.caption("Based on live 2-year Pearson r(ticker, BNO) × GPR shock magnitude")

    asset_impacts = result["asset_impacts"]
    sorted_assets = sorted(asset_impacts.items(), key=lambda x: x[1])
    tkrs       = [a[0] for a in sorted_assets]
    impacts    = [a[1] for a in sorted_assets]
    bar_colors = ["#f85149" if v < 0 else "#3fb950" for v in impacts]

    fig = go.Figure(go.Bar(
        x=impacts, y=tkrs,
        orientation="h",
        marker_color=bar_colors,
        text=[f"{v:+.1%}" for v in impacts],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Projected: %{x:.1%}<extra></extra>",
    ))
    fig = set_dark_theme(fig)
    fig.update_layout(
        height=400,
        xaxis=dict(tickformat=".0%", title="Projected Return"),
        yaxis_title=None,
        showlegend=False,
        margin=dict(l=0, r=80, t=20, b=0),
    )
    fig.add_vline(x=0, line_color="#30363d", line_width=1)
    st.plotly_chart(fig, use_container_width=True)

    # ── Live sensitivity table ────────────────────────────────────────────────
    with st.expander("Live Computed Sensitivities (vs BNO weekly returns, 2Y)"):
        sens_rows = [
            {
                "Ticker":      tkr,
                "Sensitivity": f"{sensitivities.get(tkr, 0):+.4f}",
                "Direction":   "Safe Haven" if sensitivities.get(tkr, 0) > 0 else "Risk-Off",
                "Expected at +100pt GPR": f"{sensitivities.get(tkr, 0):+.1%}",
            }
            for tkr in sorted(TICKERS, key=lambda t: sensitivities.get(t, 0))
        ]
        st.dataframe(pl.DataFrame(sens_rows), use_container_width=True, hide_index=True)
        st.caption("Pearson r(ticker weekly return, BNO weekly return) × 0.18 · Cached 1hr")

    # ── Comparable historical events ──────────────────────────────────────────
    st.divider()
    st.markdown("### Comparable Historical Events")

    # Try live GPR index first — auto-discovers all events including 2025+
    _gpr_df = pl.DataFrame()
    try:
        from src.data.fetchers import fetch_gpr_index
        _gpr_df = fetch_gpr_index()
    except Exception:
        pass

    if not _gpr_df.is_empty() and "gpr" in _gpr_df.columns:
        # Find local peaks in the GPR series above threshold (spike events)
        gpr_vals   = _gpr_df["gpr"].to_list()
        gpr_dates  = _gpr_df["date"].to_list()
        threshold  = 100.0   # only flag meaningful spikes

        # Known event labels keyed by approximate date (for annotation)
        _KNOWN_LABELS = {d: lbl for d, lbl in KEY_EVENTS}

        spike_events: list[dict] = []
        for i in range(1, len(gpr_vals) - 1):
            v = gpr_vals[i]
            if v < threshold:
                continue
            if v >= gpr_vals[i - 1] and v >= gpr_vals[i + 1]:
                dt_str = str(gpr_dates[i])
                label  = _KNOWN_LABELS.get(
                    min(_KNOWN_LABELS.keys(), key=lambda d: abs((
                        __import__("datetime").date.fromisoformat(str(d)) -
                        __import__("datetime").date.fromisoformat(dt_str[:10])
                    ).days)),
                    dt_str[:7],
                ) if _KNOWN_LABELS else dt_str[:7]
                spike_events.append({"label": label, "date": dt_str[:10], "gpr": round(v, 1)})

        # Sort by closeness to the user's input shock
        spike_events.sort(key=lambda x: abs(gpr_delta - x["gpr"]))
        top4 = spike_events[:4] if spike_events else []

        if top4:
            comparables = [
                {
                    "Event":        e["label"],
                    "Date":         e["date"],
                    "Actual GPR":   f"{e['gpr']:.0f} pts",
                    "vs Your Input": f"{e['gpr'] - gpr_delta:+.0f} pts",
                    "Similarity":   f"{max(0, 100 - abs(gpr_delta - e['gpr'])):.0f}%",
                }
                for e in top4
            ]
            st.caption(
                f"Live GPR index · Caldara-Iacoviello · "
                f"{str(_gpr_df['date'].min())[:7]} → {str(_gpr_df['date'].max())[:7]} · "
                f"{len(spike_events)} spike events detected above {threshold:.0f} pts"
            )
            st.dataframe(pl.DataFrame(comparables), use_container_width=True, hide_index=True)
        else:
            st.info("No GPR spikes above threshold found in live data.")
    else:
        # Fallback: extended hardcoded list including 2025 events
        # 2025 magnitudes estimated from Brent vol + equity market reaction
        _HISTORICAL_GPR = {
            "Arab Spring (Dec 2010)":           60,
            "Russia-Crimea (Feb 2014)":         70,
            "Oil Price Collapse (Jun 2014)":    65,
            "Aramco Attack (Sep 2019)":         80,
            "Soleimani Strike (Jan 2020)":      90,
            "COVID Declared (Mar 2020)":       150,
            "Ukraine Invasion (Feb 2022)":     180,
            "Hamas Attack (Oct 2023)":          75,
            "Red Sea Disruption (Jan 2024)":    65,
            "Gaza Ceasefire (Jan 2025)":        60,   # estimated — de-escalation phase
            "US Liberation Day Tariffs (Apr 2025)": 85,  # estimated — market selloff proxy
        }
        comparables = [
            {
                "Event":     ev,
                "GPR Shock": f"~{g} pts",
                "Similarity": f"{max(0, 100 - abs(gpr_delta - g)):.0f}%",
            }
            for ev, g in sorted(_HISTORICAL_GPR.items(), key=lambda x: abs(gpr_delta - x[1]))[:5]
        ]
        st.caption("Live GPR fetch unavailable · Extended fallback list · 2025 magnitudes estimated")
        st.dataframe(pl.DataFrame(comparables), use_container_width=True, hide_index=True)
