"""
tab7_research.py — Equity Research
Per-ticker fundamentals, DCF model, analyst consensus, price chart.
Live data via yfinance. Regime overlay from VARTA engine.
"""

import polars as pl
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf
from src.data.fetchers import fetch_alpaca_portfolio
from src.data.loaders import load_regimes
from src.models.regime import get_current_regime
from src.models.kronos_live import generate_forecast, is_available as kronos_available, get_load_error
from src.models.kronos import get_ticker_forecast as _get_demo_forecast
from src.utils import set_dark_theme
from config import ASSETS, TICKERS, RISK_FREE_RATE, GEORISK_SENSITIVITY, FINNHUB_API_KEY, KRONOS_PRED_LEN


@st.cache_data(ttl=3600)
def _get_fundamentals(ticker: str) -> dict:
    """Fetch yfinance fundamentals for a ticker. Cached 1hr."""
    try:
        info = yf.Ticker(ticker).info
        return {
            "name":           info.get("longName", ticker),
            "sector":         info.get("sector", "—"),
            "market_cap":     info.get("marketCap", 0),
            "pe_ratio":       info.get("trailingPE", None),
            "fwd_pe":         info.get("forwardPE", None),
            "pb_ratio":       info.get("priceToBook", None),
            "ev_ebitda":      info.get("enterpriseToEbitda", None),
            "debt_equity":    info.get("debtToEquity", None),
            "roe":            info.get("returnOnEquity", None),
            "roa":            info.get("returnOnAssets", None),
            "gross_margin":   info.get("grossMargins", None),
            "net_margin":     info.get("profitMargins", None),
            "revenue_growth": info.get("revenueGrowth", None),
            "eps":            info.get("trailingEps", None),
            "div_yield":      info.get("dividendYield", None),
            "52w_high":       info.get("fiftyTwoWeekHigh", None),
            "52w_low":        info.get("fiftyTwoWeekLow", None),
            "target_price":   info.get("targetMeanPrice", None),
            "recommendation": info.get("recommendationKey", "—"),
            "analyst_count":  info.get("numberOfAnalystOpinions", 0),
        }
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def _get_price_history(ticker: str, period: str = "1y") -> pl.DataFrame:
    """Fetch OHLCV history via yfinance. Handles MultiIndex columns. Cached 1hr."""
    try:
        raw = yf.download(ticker, period=period, interval="1d",
                          auto_adjust=True, progress=False,
                          multi_level_index=False)
        if raw.empty:
            return pl.DataFrame()

        rows = []
        for idx, row in raw.iterrows():
            rows.append({
                "date":   idx.date(),
                "open":   float(row["Open"]),
                "high":   float(row["High"]),
                "low":    float(row["Low"]),
                "close":  float(row["Close"]),
                "volume": float(row["Volume"]),
            })
        return pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Date))
    except Exception as e:
        return pl.DataFrame()


@st.cache_data(ttl=3600)
def _compute_dcf(ticker: str, growth: float, discount: float, terminal: float, years: int = 5) -> dict:
    """
    Simple DCF using yfinance free cash flow as base.
    Cached 1hr — slider interactions reuse this result without re-fetching.

    Args:
        ticker: Ticker symbol.
        growth: Annual revenue growth rate as decimal (e.g. 0.08 = 8%).
        discount: Discount rate as decimal (e.g. 0.10 = 10%).
        terminal: Terminal growth rate as decimal (e.g. 0.03 = 3%).
        years: Projection horizon in years.
    Returns:
        Dict with DCF results, or empty dict if data unavailable.
    """
    try:
        if discount <= terminal:
            return {}   # Gordon Growth Model undefined when discount ≤ terminal growth

        tkr_obj  = yf.Ticker(ticker)          # single instance — reused for all fields
        fcf_data = tkr_obj.cashflow
        if fcf_data is None or fcf_data.empty:
            return {}
        fcf_row = fcf_data.loc["Free Cash Flow"] if "Free Cash Flow" in fcf_data.index else None
        if fcf_row is None:
            return {}
        base_fcf = float(fcf_row.iloc[0])
        if base_fcf <= 0:
            return {}

        projections = []
        for yr in range(1, years + 1):
            fcf_yr = base_fcf * ((1 + growth) ** yr)
            pv     = fcf_yr / ((1 + discount) ** yr)
            projections.append({"year": yr, "fcf": fcf_yr, "pv": pv})

        terminal_value = (base_fcf * (1 + growth) ** years * (1 + terminal)) / (discount - terminal)
        terminal_pv    = terminal_value / ((1 + discount) ** years)
        total_pv       = sum(p["pv"] for p in projections) + terminal_pv

        # Use fast_info for both shares and price — avoids the heavy .info call
        fast   = tkr_obj.fast_info
        shares  = getattr(fast, "shares", None)
        current = getattr(fast, "last_price", None)
        intrinsic = total_pv / shares if shares and shares > 0 else None
        upside    = ((intrinsic / current) - 1) if intrinsic and current else None

        return {
            "base_fcf":      base_fcf,
            "projections":   projections,
            "terminal_pv":   terminal_pv,
            "total_pv":      total_pv,
            "intrinsic":     intrinsic,
            "current_price": current,
            "upside":        upside,
        }
    except Exception:
        return {}


def _compute_indicators(closes: list[float]) -> dict:
    """
    Compute RSI-14, Bollinger Bands (20,2), and MACD (12,26,9) from close prices.
    Pure Python — no pandas or numpy dependency.

    Args:
        closes: List of closing prices in chronological order.
    Returns:
        Dict with keys: rsi, bb_upper, bb_mid, bb_lower, macd, signal, histogram
        Each value is a list aligned to the closes list (None for warm-up period).
    """
    n = len(closes)

    # ── RSI-14 ────────────────────────────────────────────────────────────────
    rsi: list[float | None] = [None] * n
    if n >= 15:
        gains, losses = [], []
        for i in range(1, n):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0.0))
            losses.append(max(-diff, 0.0))
        avg_gain = sum(gains[:14]) / 14
        avg_loss = sum(losses[:14]) / 14
        for i in range(14, n):
            avg_gain = (avg_gain * 13 + gains[i - 1]) / 14
            avg_loss = (avg_loss * 13 + losses[i - 1]) / 14
            rs = avg_gain / avg_loss if avg_loss > 0 else 100.0
            rsi[i] = round(100 - 100 / (1 + rs), 2)

    # ── Bollinger Bands (20, 2σ) ──────────────────────────────────────────────
    bb_upper: list[float | None] = [None] * n
    bb_mid:   list[float | None] = [None] * n
    bb_lower: list[float | None] = [None] * n
    for i in range(19, n):
        window = closes[i - 19: i + 1]
        mu  = sum(window) / 20
        std = (sum((x - mu) ** 2 for x in window) / 20) ** 0.5
        bb_mid[i]   = round(mu, 4)
        bb_upper[i] = round(mu + 2 * std, 4)
        bb_lower[i] = round(mu - 2 * std, 4)

    # ── MACD (12, 26, 9) ──────────────────────────────────────────────────────
    def _ema(prices: list[float], period: int) -> list[float | None]:
        result: list[float | None] = [None] * len(prices)
        k = 2 / (period + 1)
        for i in range(period - 1, len(prices)):
            if result[i - 1] is None:
                result[i] = sum(prices[i - period + 1: i + 1]) / period
            else:
                result[i] = prices[i] * k + result[i - 1] * (1 - k)  # type: ignore[operator]
        return result

    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line: list[float | None] = [
        round(a - b, 4) if a is not None and b is not None else None
        for a, b in zip(ema12, ema26)
    ]
    valid_macd = [(i, v) for i, v in enumerate(macd_line) if v is not None]
    signal_line: list[float | None] = [None] * n
    if len(valid_macd) >= 9:
        vals = [v for _, v in valid_macd]
        ema_s = _ema(vals, 9)
        for j, (i, _) in enumerate(valid_macd):
            signal_line[i] = ema_s[j]

    histogram: list[float | None] = [
        round(m - s, 4) if m is not None and s is not None else None
        for m, s in zip(macd_line, signal_line)
    ]

    return {
        "rsi":       rsi,
        "bb_upper":  bb_upper,
        "bb_mid":    bb_mid,
        "bb_lower":  bb_lower,
        "macd":      macd_line,
        "signal":    signal_line,
        "histogram": histogram,
    }


@st.cache_data(ttl=3600)
def _get_earnings_calendar(ticker: str) -> list[dict]:
    """
    Fetch upcoming earnings dates from Finnhub for a given ticker.
    Falls back to yfinance calendar if Finnhub unavailable.
    Cached 1 hour.

    Args:
        ticker: Ticker symbol.
    Returns:
        List of dicts with keys: date, eps_estimate, revenue_estimate
    """
    import requests
    from datetime import date, timedelta

    results = []

    # Try Finnhub first
    if FINNHUB_API_KEY:
        try:
            date_from = date.today().strftime("%Y-%m-%d")
            date_to   = (date.today() + timedelta(days=90)).strftime("%Y-%m-%d")
            resp = requests.get(
                "https://finnhub.io/api/v1/calendar/earnings",
                params={"from": date_from, "to": date_to, "symbol": ticker,
                        "token": FINNHUB_API_KEY},
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json().get("earningsCalendar", [])
            for e in data:
                results.append({
                    "date":             e.get("date", ""),
                    "eps_estimate":     e.get("epsEstimate"),
                    "revenue_estimate": e.get("revenueEstimate"),
                    "quarter":          e.get("quarter", ""),
                    "year":             e.get("year", ""),
                })
            if results:
                return results
        except Exception:
            pass

    # Fallback: yfinance calendar (returns dict in yfinance ≥0.2.40, DataFrame in older)
    try:
        cal = yf.Ticker(ticker).calendar
        if cal is None:
            pass
        elif isinstance(cal, dict):
            # New API: {"Earnings Date": [Timestamp(...)], "EPS Estimate": [...], ...}
            dates = cal.get("Earnings Date", [])
            eps_list = cal.get("EPS Estimate", [])
            rev_list = cal.get("Revenue Estimate", [])
            for i, d in enumerate(dates):
                results.append({
                    "date":             str(d)[:10],
                    "eps_estimate":     eps_list[i] if i < len(eps_list) else None,
                    "revenue_estimate": rev_list[i] if i < len(rev_list) else None,
                    "quarter": "", "year": "",
                })
        elif hasattr(cal, "empty") and not cal.empty:
            for col in cal.columns:
                results.append({"date": str(col)[:10], "eps_estimate": None,
                                "revenue_estimate": None, "quarter": "", "year": ""})
    except Exception:
        pass

    return results


def render(demo_mode: bool = True) -> None:
    """Render the Equity Research tab."""

    st.markdown("### Equity Research")
    st.caption("Live fundamentals · DCF model · Analyst consensus · Regime overlay")

    # ── Ticker selector ───────────────────────────────────────────────────────
    positions = fetch_alpaca_portfolio()
    portfolio_tickers = positions["ticker"].to_list() if not positions.is_empty() else []
    all_options = portfolio_tickers + [t for t in TICKERS if t not in portfolio_tickers]

    col_sel, col_regime = st.columns([2, 3])
    with col_sel:
        def _ticker_label(t: str) -> str:
            name = ASSETS.get(t, {}).get("name", "")
            return f"{t} — {name}" if name else t

        ticker_idx = st.selectbox(
            "Select ticker",
            range(len(all_options)),
            format_func=lambda i: _ticker_label(all_options[i]),
        )
        ticker = all_options[ticker_idx]

    # Use regime_info shared by app.py top bar — avoids a second independent TTL clock
    regime_info  = st.session_state.get("regime_info") or get_current_regime(demo_mode)
    regime_label = regime_info.get("label", "Normal")
    # GRS = inherent sensitivity (normalized to 0-1 where TSM=1.0) ×
    #       regime modulator (40 baseline + 60 crisis amplifier)
    # Normal regime → GRS = sensitivity/1.40 × 40   (TSM=40, NVDA=33, GLD=16)
    # Crisis regime → GRS = sensitivity/1.40 × 100  (TSM=100, NVDA=82, GLD=39)
    _sensitivity   = GEORISK_SENSITIVITY.get(ticker, 1.0)
    _crisis_prob   = regime_info.get("prob", 0.0)
    georisk = min(100.0, (_sensitivity / 1.40) * (40 + 60 * _crisis_prob) * 100 / 100)
    rc = "#f85149" if regime_label == "Crisis" else "#3fb950"

    with col_regime:
        st.markdown(f"""
        <div style='display:flex;gap:12px;margin-top:28px;flex-wrap:wrap'>
          <div style='background:#161b22;border:1px solid #30363d;border-radius:5px;
                      padding:6px 14px;font-family:IBM Plex Mono,monospace'>
            <span style='font-size:9px;color:#8b949e;letter-spacing:1px'>REGIME</span><br>
            <span style='color:{rc};font-weight:700;font-size:13px'>{regime_label.upper()} {regime_info.get("prob",0):.0%}</span>
          </div>
          <div style='background:#161b22;border:1px solid #30363d;border-radius:5px;
                      padding:6px 14px;font-family:IBM Plex Mono,monospace'>
            <span style='font-size:9px;color:#8b949e;letter-spacing:1px'>GEORISK SCORE</span><br>
            <span style='color:{"#f85149" if georisk>60 else "#e3b341" if georisk>35 else "#3fb950"};
                         font-weight:700;font-size:13px'>{georisk:.0f} / 100</span>
          </div>
          <div style='background:#161b22;border:1px solid #30363d;border-radius:5px;
                      padding:6px 14px;font-family:IBM Plex Mono,monospace'>
            <span style='font-size:9px;color:#8b949e;letter-spacing:1px'>CATEGORY</span><br>
            <span style='color:#c9d1d9;font-size:13px'>{ASSETS.get(ticker,{}).get("category","—")}</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ── Controls row ──────────────────────────────────────────────────────────
    ctrl1, ctrl2, ctrl3 = st.columns([2, 2, 2])
    with ctrl1:
        period_map = {"1M": "1mo", "3M": "3mo", "1Y": "1y", "2Y": "2y", "5Y": "5y"}
        period_sel = st.segmented_control("Period", list(period_map.keys()), default="1Y")
        period     = period_map.get(period_sel or "1Y", "1y")
    with ctrl2:
        show_indicators = st.selectbox(
            "Indicators",
            ["None", "Bollinger Bands", "RSI", "MACD", "All"],
            index=0,
        )
    with ctrl3:
        show_kronos = st.checkbox(
            "Kronos Forecast",
            value=False,
            help=(
                f"Run Kronos financial foundation model for {KRONOS_PRED_LEN}-day OHLCV forecast. "
                "Model: NeoQuasar/Kronos-small (24.7M params). "
                "Trained on 45+ exchanges. Outputs full candlestick bars beyond last historical date. "
                "First run downloads ~100MB from HuggingFace."
            ),
        )

    with st.spinner(f"Loading {ticker}..."):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as _pool:
            _hist_fut = _pool.submit(_get_price_history, ticker, period)
            _info_fut = _pool.submit(_get_fundamentals, ticker)
        hist = _hist_fut.result()
        info = _info_fut.result()

    # ── Price chart with technical indicators ─────────────────────────────────
    if not hist.is_empty():
        dates  = hist["date"].to_list()
        closes = hist["close"].to_list()
        indics = _compute_indicators(closes)

        # Decide subplot layout based on selected indicators
        show_rsi  = show_indicators in ("RSI", "All")
        show_macd = show_indicators in ("MACD", "All")
        n_rows    = 1 + int(show_rsi) + int(show_macd)
        row_heights = [0.6] + [0.2] * (n_rows - 1) if n_rows > 1 else [1.0]

        fig = make_subplots(
            rows=n_rows, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.04,
            row_heights=row_heights,
            subplot_titles=(
                [f"{ticker} — Price"] +
                (["RSI (14)"] if show_rsi else []) +
                (["MACD (12,26,9)"] if show_macd else [])
            ),
        )

        # Candlestick (row 1)
        fig.add_trace(go.Candlestick(
            x=dates,
            open=hist["open"].to_list(),
            high=hist["high"].to_list(),
            low=hist["low"].to_list(),
            close=closes,
            name=ticker,
            increasing_line_color="#3fb950",
            decreasing_line_color="#f85149",
            increasing_fillcolor="rgba(63,185,80,0.25)",
            decreasing_fillcolor="rgba(248,81,73,0.25)",
        ), row=1, col=1)

        # Moving averages — vectorized via Polars (Rust) instead of O(n²) Python loops
        if len(hist) >= 50:
            ma50 = hist.with_columns(
                pl.col("close").rolling_mean(window_size=50, min_samples=1).alias("ma50")
            )["ma50"].to_list()
            fig.add_trace(go.Scatter(x=dates, y=ma50, name="50 MA",
                line=dict(color="#58a6ff", width=1.2, dash="dot")), row=1, col=1)
        if len(hist) >= 200:
            ma200 = hist.with_columns(
                pl.col("close").rolling_mean(window_size=200, min_samples=1).alias("ma200")
            )["ma200"].to_list()
            fig.add_trace(go.Scatter(x=dates, y=ma200, name="200 MA",
                line=dict(color="#e3b341", width=1.2, dash="dot")), row=1, col=1)

        # Bollinger Bands (on price chart)
        if show_indicators in ("Bollinger Bands", "All"):
            fig.add_trace(go.Scatter(
                x=dates, y=indics["bb_upper"], name="BB Upper",
                line=dict(color="rgba(88,166,255,0.4)", width=1, dash="dot"),
                showlegend=True,
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=dates, y=indics["bb_lower"], name="BB Lower",
                line=dict(color="rgba(88,166,255,0.4)", width=1, dash="dot"),
                fill="tonexty", fillcolor="rgba(88,166,255,0.05)",
                showlegend=True,
            ), row=1, col=1)

        # Regime shading — clipped to the current chart window so short periods
        # (1M, 3M, 1Y) don't get their x-axis blown out to 2010-2024
        _chart_start = hist.sort("date")["date"][0]
        _chart_end   = hist.sort("date")["date"][-1]
        regimes_df = load_regimes(demo_mode)
        if not regimes_df.is_empty():
            reg = (
                regimes_df
                .filter((pl.col("date") >= _chart_start) & (pl.col("date") <= _chart_end))
                .sort("date")
            )
            if not reg.is_empty():
                start_r = None
                for d, lbl in zip(reg["date"].to_list(), reg["regime_label"].to_list()):
                    if lbl == "Crisis" and start_r is None:
                        start_r = d
                    elif lbl != "Crisis" and start_r is not None:
                        fig.add_vrect(x0=start_r, x1=d, fillcolor="#f85149",
                                      opacity=0.07, layer="below", line_width=0, row=1, col=1)
                        start_r = None
                if start_r:
                    fig.add_vrect(x0=start_r, x1=reg["date"].to_list()[-1],
                                  fillcolor="#f85149", opacity=0.07, layer="below",
                                  line_width=0, row=1, col=1)

        # ── Kronos OHLCV forecast (shiyu-coder/Kronos) ────────────────────────
        # Cache key: ticker + period — reuse result until ticker or period changes
        _k_cache_key  = f"kronos_fc_{ticker}_{period}"
        _k_date_key   = f"kronos_last_date_{ticker}_{period}"
        _current_last = str(hist.sort("date")["date"][-1]) if not hist.is_empty() else ""
        kronos_fc: pl.DataFrame | None = None
        if show_kronos:
            if not kronos_available():
                # Live model not available (cloud / no repo) — use pre-computed demo forecasts
                _demo_fc = _get_demo_forecast(ticker, demo_mode=True)
                if not _demo_fc.is_empty():
                    # Demo CSV uses forecast_date; chart expects date + OHLC columns
                    kronos_fc = _demo_fc.rename({"forecast_date": "date"}).with_columns([
                        pl.col("mean").alias("close"),
                        pl.col("mean").alias("open"),
                        pl.col("high_80").alias("high"),
                        pl.col("low_80").alias("low"),
                        pl.lit(0).alias("volume"),
                    ])
                    st.caption("Kronos forecast: pre-computed (live model unavailable in this environment)")
            elif (
                _k_cache_key in st.session_state
                and st.session_state.get(_k_date_key) == _current_last
            ):
                kronos_fc = st.session_state[_k_cache_key]  # cache still fresh
            else:
                with st.spinner(
                    f"Running Kronos ({KRONOS_PRED_LEN}-day OHLCV forecast) — "
                    "first run loads model weights, ~10s..."
                ):
                    # Kronos needs ≥252 bars of context — 1M display period (~21 bars)
                    # is far too short. Fetch 1Y for inference, keep hist for display.
                    _kronos_input = hist
                    if period == "1mo" and len(hist) < 252:
                        _kronos_ctx = _get_price_history(ticker, "1y")
                        if not _kronos_ctx.is_empty() and len(_kronos_ctx) >= 60:
                            _kronos_input = _kronos_ctx

                    kronos_fc = generate_forecast(_kronos_input, pred_len=KRONOS_PRED_LEN)
                    st.session_state[_k_cache_key] = kronos_fc
                    st.session_state[_k_date_key]  = _current_last  # staleness sentinel

                if kronos_fc is None:
                    err = get_load_error()
                    st.error(f"Kronos inference failed: {err or 'unknown error'}")

        if kronos_fc is not None and not kronos_fc.is_empty():
            k_dates = [str(d) for d in kronos_fc["date"].to_list()]
            k_open  = kronos_fc["open"].to_list()
            k_high  = kronos_fc["high"].to_list()
            k_low   = kronos_fc["low"].to_list()
            k_close = kronos_fc["close"].to_list()
            k_origin = k_dates[0]

            # Forecast candlestick bars (orange, semi-transparent)
            fig.add_trace(go.Candlestick(
                x=k_dates,
                open=k_open,
                high=k_high,
                low=k_low,
                close=k_close,
                name="Kronos Forecast",
                increasing_line_color="rgba(255,163,26,0.9)",
                decreasing_line_color="rgba(255,100,80,0.9)",
                increasing_fillcolor="rgba(255,163,26,0.30)",
                decreasing_fillcolor="rgba(255,100,80,0.30)",
            ), row=1, col=1)

            # Forecast mid-line (close prices)
            fig.add_trace(go.Scatter(
                x=k_dates, y=k_close,
                name="Kronos Close",
                line=dict(color="rgba(255,163,26,0.6)", width=1.2, dash="dot"),
                hovertemplate="Kronos: $%{y:.2f}<extra></extra>",
                showlegend=False,
            ), row=1, col=1)

            # High/Low band (soft shading)
            fig.add_trace(go.Scatter(
                x=k_dates + k_dates[::-1],
                y=k_high + k_low[::-1],
                fill="toself",
                fillcolor="rgba(255,163,26,0.06)",
                line=dict(width=0),
                name="Kronos H/L Band",
                showlegend=True,
                hoverinfo="skip",
            ), row=1, col=1)

            # Vertical divider at forecast boundary
            fig.add_vline(
                x=str(k_origin),
                line_width=1, line_dash="dot",
                line_color="rgba(255,163,26,0.6)",
            )
            fig.add_annotation(
                x=str(k_origin), y=0.97,
                xref="x", yref="paper",
                text="KRONOS →",
                showarrow=False,
                font=dict(size=9, color="#FFA31A", family="IBM Plex Mono"),
                xanchor="left",
            )

        # RSI subplot
        rsi_row = 2 if show_rsi else None
        if show_rsi and rsi_row:
            fig.add_trace(go.Scatter(
                x=dates, y=indics["rsi"], name="RSI",
                line=dict(color="#a371f7", width=1.5),
            ), row=rsi_row, col=1)
            fig.add_hline(y=70, line_dash="dot", line_color="#f85149",
                          opacity=0.5, row=rsi_row, col=1)
            fig.add_hline(y=30, line_dash="dot", line_color="#3fb950",
                          opacity=0.5, row=rsi_row, col=1)
            fig.add_hrect(y0=70, y1=100, fillcolor="#f85149",
                          opacity=0.05, layer="below", line_width=0,
                          row=rsi_row, col=1)
            fig.add_hrect(y0=0, y1=30, fillcolor="#3fb950",
                          opacity=0.05, layer="below", line_width=0,
                          row=rsi_row, col=1)

        # MACD subplot
        macd_row = (2 if show_macd and not show_rsi else 3) if show_macd else None
        if show_macd and macd_row:
            colors = [
                "#3fb950" if (v or 0) >= 0 else "#f85149"
                for v in indics["histogram"]
            ]
            fig.add_trace(go.Bar(
                x=dates, y=indics["histogram"], name="Histogram",
                marker_color=colors, opacity=0.6,
            ), row=macd_row, col=1)
            fig.add_trace(go.Scatter(
                x=dates, y=indics["macd"], name="MACD",
                line=dict(color="#58a6ff", width=1.3),
            ), row=macd_row, col=1)
            fig.add_trace(go.Scatter(
                x=dates, y=indics["signal"], name="Signal",
                line=dict(color="#e3b341", width=1.3, dash="dot"),
            ), row=macd_row, col=1)

        fig = set_dark_theme(fig)
        total_height = 420 + 150 * (n_rows - 1)
        fig.update_layout(
            height=total_height,
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            hovermode="x unified",
            margin=dict(t=30, b=10),
        )
        if show_rsi and rsi_row:
            fig.update_yaxes(range=[0, 100], row=rsi_row, col=1)

        # Explicitly pin x-axis to the selected period — prevents regime vrects
        # or any other trace from expanding the range beyond the chosen window
        _x_end = (
            str(kronos_fc.sort("date")["date"][-1])
            if (kronos_fc is not None and not kronos_fc.is_empty())
            else str(_chart_end)
        )
        fig.update_xaxes(range=[str(_chart_start), _x_end])

        st.plotly_chart(fig, width="stretch")

        # ── Live RSI / BB signal summary ──────────────────────────────────────
        last_rsi = next((v for v in reversed(indics["rsi"]) if v is not None), None)
        last_bb_upper = next((v for v in reversed(indics["bb_upper"]) if v is not None), None)
        last_bb_lower = next((v for v in reversed(indics["bb_lower"]) if v is not None), None)
        last_close = closes[-1] if closes else None
        last_macd  = next((v for v in reversed(indics["macd"]) if v is not None), None)
        last_signal= next((v for v in reversed(indics["signal"]) if v is not None), None)

        sig_parts = []
        if last_rsi is not None:
            rsi_color = "#f85149" if last_rsi > 70 else "#3fb950" if last_rsi < 30 else "#e3b341"
            rsi_lbl   = "OVERBOUGHT" if last_rsi > 70 else "OVERSOLD" if last_rsi < 30 else "NEUTRAL"
            sig_parts.append(
                f"<span style='font-family:IBM Plex Mono,monospace;font-size:11px'>"
                f"RSI&nbsp;<b style='color:{rsi_color}'>{last_rsi:.1f}</b>"
                f"&nbsp;<span style='color:{rsi_color};font-size:9px'>{rsi_lbl}</span></span>"
            )
        if last_close and last_bb_upper and last_bb_lower:
            if last_close > last_bb_upper:
                bb_lbl, bb_color = "ABOVE UPPER BAND", "#f85149"
            elif last_close < last_bb_lower:
                bb_lbl, bb_color = "BELOW LOWER BAND", "#3fb950"
            else:
                bb_lbl, bb_color = "WITHIN BANDS", "#8b949e"
            sig_parts.append(
                f"<span style='font-family:IBM Plex Mono,monospace;font-size:11px'>"
                f"BB&nbsp;<span style='color:{bb_color};font-size:9px'>{bb_lbl}</span></span>"
            )
        if last_macd is not None and last_signal is not None:
            cross_color = "#3fb950" if last_macd > last_signal else "#f85149"
            cross_lbl   = "BULLISH CROSS" if last_macd > last_signal else "BEARISH CROSS"
            sig_parts.append(
                f"<span style='font-family:IBM Plex Mono,monospace;font-size:11px'>"
                f"MACD&nbsp;<span style='color:{cross_color};font-size:9px'>{cross_lbl}</span></span>"
            )

        if sig_parts:
            st.html(
                "<div style='display:flex;gap:20px;flex-wrap:wrap;padding:8px 0;margin-bottom:4px'>"
                + "&nbsp;&nbsp;|&nbsp;&nbsp;".join(sig_parts)
                + "</div>"
            )

        # ── Kronos forecast summary card ──────────────────────────────────────
        if show_kronos and kronos_fc is not None and not kronos_fc.is_empty():
            k_anchor   = float(hist.sort("date").tail(1)["close"][0]) if not hist.is_empty() else 0.0
            k_end_close = float(kronos_fc.sort("date").tail(1)["close"][0])
            k_end_high  = float(kronos_fc.sort("date").tail(1)["high"][0])
            k_end_low   = float(kronos_fc.sort("date").tail(1)["low"][0])
            k_end_date  = str(kronos_fc.sort("date").tail(1)["date"][0])[:10]
            k_fc_ret    = ((k_end_close / k_anchor) - 1) * 100 if k_anchor > 0 else 0.0
            ret_color   = "#3fb950" if k_fc_ret >= 0 else "#f85149"

            st.html(
                "<div style='background:#161b22;border:1px solid #FFA31A30;"
                "border-left:3px solid #FFA31A;border-radius:5px;"
                "padding:10px 16px;margin-top:8px;display:flex;gap:24px;flex-wrap:wrap;"
                "font-family:IBM Plex Mono,monospace'>"
                "<div><div style='font-size:9px;color:#8b949e;letter-spacing:1px'>KRONOS MODEL</div>"
                "<div style='font-size:10px;color:#FFA31A;font-weight:700'>NeoQuasar/Kronos-small</div>"
                f"<div style='font-size:9px;color:#8b949e'>24.7M params · {KRONOS_PRED_LEN}-day OHLCV forecast · 45+ exchanges</div>"
                "</div>"
                f"<div><div style='font-size:9px;color:#8b949e;letter-spacing:1px'>ANCHOR (last close)</div>"
                f"<div style='font-size:13px;color:#c9d1d9;font-weight:700'>${k_anchor:.2f}</div></div>"
                f"<div><div style='font-size:9px;color:#8b949e;letter-spacing:1px'>FORECAST CLOSE ({k_end_date})</div>"
                f"<div style='font-size:13px;color:{ret_color};font-weight:700'>"
                f"${k_end_close:.2f} ({k_fc_ret:+.1f}%)</div></div>"
                f"<div><div style='font-size:9px;color:#8b949e;letter-spacing:1px'>FORECAST H/L RANGE</div>"
                f"<div style='font-size:13px;color:#c9d1d9'>${k_end_low:.2f} – ${k_end_high:.2f}</div></div>"
                "</div>"
            )
    else:
        st.warning(f"No price data available for {ticker}")

    # ── Fundamentals + Valuation ──────────────────────────────────────────────
    if info:
        st.divider()
        st.markdown("#### Fundamentals")

        def _fmt_pct(v): return f"{v*100:.1f}%" if v is not None else "—"
        def _fmt_x(v):   return f"{v:.1f}×"    if v is not None else "—"
        def _fmt_num(v):  return f"{v:.2f}"     if v is not None else "—"
        def _fmt_mc(v):
            if v is None: return "—"
            if v >= 1e12: return f"${v/1e12:.2f}T"
            if v >= 1e9:  return f"${v/1e9:.1f}B"
            return f"${v/1e6:.0f}M"

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Market Cap",      _fmt_mc(info.get("market_cap")))
        c2.metric("P/E (TTM)",        _fmt_x(info.get("pe_ratio")))
        c3.metric("Forward P/E",      _fmt_x(info.get("fwd_pe")))
        c4.metric("P/B",              _fmt_x(info.get("pb_ratio")))

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("EV/EBITDA",        _fmt_x(info.get("ev_ebitda")))
        c6.metric("ROE",              _fmt_pct(info.get("roe")))
        c7.metric("Net Margin",       _fmt_pct(info.get("net_margin")))
        c8.metric("Revenue Growth",   _fmt_pct(info.get("revenue_growth")))

        # Analyst consensus
        st.divider()
        st.markdown("#### Analyst Consensus")
        rec  = str(info.get("recommendation", "—")).upper()
        pt   = info.get("target_price")
        curr = info.get("52w_high")
        an   = info.get("analyst_count", 0)
        rc2  = "#3fb950" if "BUY" in rec else "#f85149" if "SELL" in rec else "#e3b341"

        ca1, ca2, ca3, ca4 = st.columns(4)
        ca1.metric("Consensus",      rec)
        ca2.metric("Mean Price Target", f"${pt:.2f}" if pt else "—")
        ca3.metric("52W High",       f"${curr:.2f}" if curr else "—")
        ca4.metric("52W Low",        f"${info.get('52w_low'):.2f}" if info.get('52w_low') else "—")

    # ── DCF Model ─────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### DCF Model")

    with st.expander("Configure assumptions", expanded=True):
        d1, d2, d3, d4 = st.columns(4)
        with d1:
            growth   = st.slider("Revenue Growth", 0, 30, 8, 1, format="%d%%",
                                  key=f"dcf_g_{ticker}") / 100
        with d2:
            discount = st.slider("Discount Rate",  5, 20, 10, 1, format="%d%%",
                                  key=f"dcf_d_{ticker}") / 100
        with d3:
            terminal = st.slider("Terminal Growth", 1.0, 5.0, 3.0, 0.5, format="%.1f%%",
                                  key=f"dcf_t_{ticker}") / 100
        with d4:
            years    = st.slider("Projection Years", 3, 10, 5, key=f"dcf_y_{ticker}")

        dcf = _compute_dcf(ticker, growth, discount, terminal, years)

        if dcf and dcf.get("intrinsic"):
            intrinsic = dcf["intrinsic"]
            current   = dcf["current_price"]
            upside    = dcf["upside"]
            up_color  = "#3fb950" if upside and upside > 0 else "#f85149"

            iv1, iv2, iv3 = st.columns(3)
            iv1.metric("Intrinsic Value",  f"${intrinsic:.2f}")
            iv2.metric("Current Price",    f"${current:.2f}" if current else "—")
            iv3.metric("Upside / Downside", f"{upside*100:+.1f}%" if upside else "—",
                        delta_color="normal")

            # FCF projection chart
            if dcf.get("projections"):
                proj = dcf["projections"]
                fig_dcf = go.Figure(go.Bar(
                    x=[f"Year {p['year']}" for p in proj],
                    y=[p["fcf"] / 1e9 for p in proj],
                    marker_color="#00FFB2",
                    name="Projected FCF ($B)",
                ))
                fig_dcf = set_dark_theme(fig_dcf)
                fig_dcf.update_layout(
                    height=220, margin=dict(t=10, b=10),
                    yaxis_title="FCF ($B)",
                    showlegend=False,
                )
                st.plotly_chart(fig_dcf, width="stretch")
        else:
            st.info("DCF unavailable — free cash flow data not available for this ticker.")

    # ── Earnings Calendar ─────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Upcoming Earnings")
    st.caption("Next 90 days · via Finnhub")

    with st.spinner("Loading earnings calendar..."):
        earnings = _get_earnings_calendar(ticker)

    if earnings:
        items_html = ""
        for e in earnings[:6]:
            eps_str = f"EPS est. ${e['eps_estimate']:.2f}" if e.get("eps_estimate") else ""
            rev_raw = e.get("revenue_estimate")
            if rev_raw:
                rev_str = f"Rev est. ${rev_raw/1e9:.2f}B" if rev_raw >= 1e9 else f"Rev est. ${rev_raw/1e6:.0f}M"
            else:
                rev_str = ""
            q_str = f"Q{e.get('quarter','')} {e.get('year','')}" if e.get("quarter") else ""
            items_html += (
                f"<div style='background:#161b22;border:1px solid #30363d;border-radius:5px;"
                f"padding:10px 14px;margin-bottom:6px;display:flex;justify-content:space-between;"
                f"align-items:center'>"
                f"<div>"
                f"<div style='font-family:IBM Plex Mono,monospace;font-size:12px;color:#00FFB2;"
                f"font-weight:700'>{e.get('date','')}</div>"
                f"<div style='font-size:10px;color:#8b949e;margin-top:2px'>{q_str}</div>"
                f"</div>"
                f"<div style='text-align:right;font-family:IBM Plex Mono,monospace;font-size:11px;"
                f"color:#c9d1d9'>{eps_str}"
                f"{'&nbsp;&nbsp;·&nbsp;&nbsp;' if eps_str and rev_str else ''}{rev_str}</div>"
                f"</div>"
            )
        st.html(f"<div>{items_html}</div>")
    else:
        st.caption(f"No upcoming earnings found for {ticker} in the next 90 days.")
