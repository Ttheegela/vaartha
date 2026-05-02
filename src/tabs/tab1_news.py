"""
tab1_news.py — Live Intelligence Feed
Tri-source news: Alpaca (Benzinga/PRN) + Finnhub (Reuters/AP/MarketWatch/CNBC)
+ WSJ/MarketWatch RSS.
BREAKING detection (<30 min), st.fragment auto-refresh every 2 min (partial rerun
— only the news section reruns, rest of page stays stable).
Trending Topics panel derived from live keyword frequency.
Polymarket crowd-sourced geo-risk signals on a separate 30-min cache.
"""

import polars as pl
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timezone, timedelta

from src.data.fetchers import (
    fetch_alpaca_news,
    fetch_finnhub_news,
    fetch_polymarket_geo,
    fetch_alpaca_portfolio,
    fetch_wsj_rss,
)
from src.utils import set_dark_theme
from config import TICKERS, ASSETS, FRED_API_KEY


# ── FRED series for Macro panel ───────────────────────────────────────────────
_FRED_SERIES = {
    "T10Y2Y":       {"label": "10Y–2Y Spread",    "unit": "%",   "invert_risk": True},
    "FEDFUNDS":     {"label": "Fed Funds Rate",    "unit": "%",   "invert_risk": False},
    "DCOILBRENTEU": {"label": "Brent Crude",       "unit": "USD", "invert_risk": False},
    "CPIAUCSL":     {"label": "CPI Index",         "unit": "idx", "invert_risk": False},
    "UNRATE":       {"label": "Unemployment",      "unit": "%",   "invert_risk": False},
}

_MACRO_KEYWORDS = [
    "fed", "federal reserve", "interest rate", "cpi", "inflation", "pce",
    "recession", "gdp", "unemployment", "yield curve", "treasury", "fomc",
    "powell", "rate cut", "rate hike", "brent", "oil price", "opec",
    "ism", "pmi", "jobs report", "payroll",
]


@st.cache_data(ttl=1800)
def _fetch_fred_indicator(series_id: str) -> tuple[float | None, float | None]:
    """
    Fetch latest value and prior value for a FRED series.
    Returns (latest, delta) — both None if unavailable.
    """
    if not FRED_API_KEY:
        return None, None
    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)
        raw = fred.get_series(series_id).dropna()
        if raw.empty or len(raw) < 2:
            return None, None
        return float(raw.iloc[-1]), float(raw.iloc[-1]) - float(raw.iloc[-2])
    except Exception:
        return None, None


@st.cache_data(ttl=3600)
def _fetch_yield_curve_series() -> pl.DataFrame:
    """Fetch 12-month 10Y-2Y spread for the yield curve sparkline."""
    if not FRED_API_KEY:
        return pl.DataFrame()
    try:
        from fredapi import Fred
        import pandas as _pd
        from datetime import datetime as _dt, timedelta as _td
        fred = Fred(api_key=FRED_API_KEY)
        start = (_dt.now() - _td(days=365)).strftime("%Y-%m-%d")
        raw = fred.get_series("T10Y2Y", observation_start=start).dropna()
        if raw.empty:
            return pl.DataFrame()
        df = pl.from_pandas(_pd.DataFrame({"date": raw.index, "value": raw.values}))
        return df.with_columns(pl.col("date").cast(pl.Date)).sort("date")
    except Exception:
        return pl.DataFrame()

# ── Constants ─────────────────────────────────────────────────────────────────
_BREAKING_SECS = 1800   # 30-min window for BREAKING badge
_FEED_REFRESH  = 120    # st.fragment run_every interval (seconds)

# ── Geo-risk keywords ─────────────────────────────────────────────────────────
_GEO_KEYWORDS = [
    "taiwan", "strait", "china", "russia", "ukraine", "iran", "hormuz",
    "red sea", "houthi", "sanctions", "tariff", "trade war", "rare earth",
    "lithium", "semiconductor", "export control", "chip ban", "geopolit",
    "military", "missile", "invasion", "conflict", "opec", "brent",
]

_BEAR_WORDS = [
    "warns", "falls", "drops", "risk", "tension", "sanction", "disruption",
    "decline", "loss", "crash", "fear", "threat", "tariff", "ban", "restrict",
    "cut", "miss", "below", "collapse", "plunge", "surge in costs", "downgrade",
    "layoff", "recall", "investigation", "fine", "penalty", "halt", "suspend",
]

_BULL_WORDS = [
    "surges", "rises", "beats", "record", "growth", "expands", "launches",
    "strong", "profit", "upgrade", "above", "gain", "rally", "boom", "demand",
    "wins", "deal", "partnership", "invest", "buyback", "dividend", "raised",
    "guidance", "outperform", "beat", "accelerate",
]

# Trending topic clusters (VARTA thesis events)
_TOPIC_CLUSTERS: dict[str, list[str]] = {
    "Taiwan / China":     ["taiwan", "china", "beijing", "tsmc", "strait", "pla"],
    "Russia / Ukraine":   ["ukraine", "russia", "zelensky", "kyiv", "moscow", "ceasefire"],
    "Iran / Middle East": ["iran", "hormuz", "houthi", "red sea", "israel", "tehran"],
    "Fed / Rates":        ["federal reserve", "fed ", "interest rate", "inflation", "powell", "fomc"],
    "AI / Chips":         ["nvidia", "amd", "gpu", " ai ", "chip", "semiconductor"],
    "Rare Earths":        ["rare earth", "lithium", "cobalt", "gallium", "germanium", "remx"],
    "Energy":             ["oil", "brent", "opec", "natural gas", "lng", "crude"],
    "Trade War":          ["tariff", "trade war", "export control", "sanction", "ban chip"],
}

_TOPIC_COLORS: dict[str, str] = {
    "Taiwan / China":     "#f85149",
    "Russia / Ukraine":   "#58a6ff",
    "Iran / Middle East": "#e3b341",
    "Fed / Rates":        "#a371f7",
    "AI / Chips":         "#00FFB2",
    "Rare Earths":        "#3fb950",
    "Energy":             "#f59e0b",
    "Trade War":          "#fb923c",
}

_SOURCE_DISPLAY = {
    "benzinga":      "Benzinga",
    "finnhub":       "Finnhub",
    "reuters":       "Reuters",
    "ap":            "AP News",
    "marketwatch":   "MarketWatch",
    "cnbc":          "CNBC",
    "bloomberg":     "Bloomberg",
    "globenewswire": "Globe Newswire",
    "prnewswire":    "PR Newswire",
    "seekingalpha":  "Seeking Alpha",
    "thestreet":     "TheStreet",
    "wsj":           "WSJ",
}

SENTIMENT_COLORS = {
    "BEARISH": ("#f85149", "#f8514918", "#f8514940"),
    "BULLISH": ("#3fb950", "#3fb95018", "#3fb95040"),
    "NEUTRAL": ("#e3b341", "#e3b34118", "#e3b34140"),
}


# ── Pure helpers (no Streamlit calls) ────────────────────────────────────────

def _source_display(raw: str) -> str:
    """Normalize raw source string to clean display name."""
    low = raw.lower().replace(" ", "").replace(".", "").replace("-", "")
    for key, label in _SOURCE_DISPLAY.items():
        if key in low:
            return label
    return raw.title() if raw else "News"


def _sentiment(headline: str, summary: str) -> tuple[str, str]:
    """Keyword-based sentiment. Returns (css_class, label)."""
    text = (headline + " " + summary).lower()
    bear = sum(1 for w in _BEAR_WORDS if w in text)
    bull = sum(1 for w in _BULL_WORDS if w in text)
    if bear > bull:
        return "badge-bear", "BEARISH"
    if bull > bear:
        return "badge-bull", "BULLISH"
    return "badge-neut", "NEUTRAL"


def _is_geo(headline: str, summary: str) -> bool:
    """True if article contains geopolitical keywords."""
    text = (headline + " " + summary).lower()
    return any(kw in text for kw in _GEO_KEYWORDS)


def _time_ago(dt) -> str:
    """Convert datetime (tz-aware or string) to '14min ago' format."""
    try:
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        mins  = int(delta.total_seconds() / 60)
        if mins < 1:    return "just now"
        if mins < 60:   return f"{mins}m ago"
        if mins < 1440: return f"{mins // 60}h ago"
        return f"{mins // 1440}d ago"
    except Exception:
        return ""


def _is_breaking(dt) -> bool:
    """True if article was published within the last 30 minutes."""
    try:
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() < _BREAKING_SECS
    except Exception:
        return False


def _merge_sources(
    alpaca: pl.DataFrame,
    finnhub: pl.DataFrame,
    wsj: pl.DataFrame,
) -> pl.DataFrame:
    """Merge and deduplicate Alpaca + Finnhub + WSJ/MarketWatch by headline."""
    frames = []
    if not alpaca.is_empty():
        frames.append(alpaca.with_columns(pl.lit("alpaca").alias("feed")))
    if not finnhub.is_empty():
        frames.append(finnhub.with_columns(pl.lit("finnhub").alias("feed")))
    if not wsj.is_empty():
        frames.append(wsj.with_columns(pl.lit("wsj").alias("feed")))
    if not frames:
        return pl.DataFrame()

    combined = (
        pl.concat(frames, how="diagonal_relaxed")
        .with_columns(pl.col("headline").str.to_lowercase().str.strip_chars().alias("_key"))
        .unique(subset=["_key"], keep="first")
        .drop("_key")
    )
    if "published_at" in combined.columns:
        try:
            combined = combined.sort("published_at", descending=True)
        except Exception:
            pass
    return combined


def _trending_topics(news: pl.DataFrame) -> list[dict]:
    """
    Derive trending topics from the last 2 hours of articles via keyword frequency.
    Returns list of {topic, count} sorted descending.
    """
    if news.is_empty():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    recent = news
    if "published_at" in news.columns:
        try:
            recent = news.filter(pl.col("published_at") >= cutoff)
        except Exception:
            pass
    if recent.is_empty():
        recent = news.head(60)

    texts = [
        (r.get("headline", "") + " " + r.get("summary", "")).lower()
        for r in recent.to_dicts()
    ]

    results = [
        {"topic": topic, "count": sum(1 for t in texts if any(kw in t for kw in kws))}
        for topic, kws in _TOPIC_CLUSTERS.items()
    ]
    return sorted([r for r in results if r["count"] > 0], key=lambda x: x["count"], reverse=True)[:8]


# ── Fragment: live news feed (reruns every 2 min automatically) ───────────────

@st.fragment(run_every=_FEED_REFRESH)
def _live_feed_fragment(demo_mode: bool) -> None:
    """
    Auto-refreshing fragment for the full news feed.
    st.fragment(run_every=120) causes only this section to rerun every 2 minutes
    — the rest of the page (top bar, sidebar, other tabs) stays stable.
    """
    positions         = fetch_alpaca_portfolio()
    portfolio_tickers = positions["ticker"].to_list() if not positions.is_empty() else TICKERS

    # ── Fetch ─────────────────────────────────────────────────────────────────
    wsj_news     = fetch_wsj_rss()
    alpaca_news  = fetch_alpaca_news(tickers=tuple(TICKERS), limit=50)
    finnhub_news = fetch_finnhub_news(tickers=tuple(TICKERS[:8]), limit=30)
    news         = _merge_sources(alpaca_news, finnhub_news, wsj_news)

    # ── BREAKING strip ────────────────────────────────────────────────────────
    if not news.is_empty():
        breaking_rows = [
            r for r in news.head(100).to_dicts()
            if _is_breaking(r.get("published_at"))
        ]
        if breaking_rows:
            ticker_text = "  ▸  ".join(
                r["headline"][:80] + ("…" if len(r["headline"]) > 80 else "")
                for r in breaking_rows[:10]
            )
            st.html(
                "<div style='background:#f8514910;border:1px solid #f8514940;"
                "border-radius:6px;padding:8px 16px;margin-bottom:14px;"
                "display:flex;align-items:center;gap:12px;overflow:hidden'>"
                "<span style='font-size:9px;font-weight:700;color:#f85149;"
                "font-family:IBM Plex Mono,monospace;letter-spacing:1.5px;"
                "white-space:nowrap;border:1px solid #f8514960;padding:2px 6px;"
                "border-radius:3px'>⚡ BREAKING</span>"
                f"<span style='font-size:11px;color:#c9d1d9;overflow:hidden;"
                f"text-overflow:ellipsis;white-space:nowrap'>{ticker_text}</span>"
                "</div>"
            )

    # ── Polymarket + Trending Topics ──────────────────────────────────────────
    poly_col, trend_col = st.columns([3, 2])

    with poly_col:
        with st.expander("🔮 Polymarket — Geopolitical Probabilities", expanded=True):
            poly_df = fetch_polymarket_geo(max_markets=8)
            if poly_df.is_empty():
                st.caption("Polymarket data unavailable.")
            else:
                _cat_color = {
                    "China / Taiwan":   "#f85149",
                    "Iran":             "#e3b341",
                    "Russia / Ukraine": "#58a6ff",
                    "US Macro":         "#a371f7",
                    "Geopolitical":     "#00FFB2",
                }
                cat_chunks: dict[str, list] = {}
                for row in poly_df.to_dicts():
                    cat_chunks.setdefault(row["category"], []).append(row)

                poly_parts: list[str] = []
                for cat, markets in sorted(cat_chunks.items()):
                    color = _cat_color.get(cat, "#00FFB2")
                    part = (
                        f"<div style='margin-bottom:14px'>"
                        f"<div style='font-size:9px;color:{color};letter-spacing:1.5px;"
                        f"text-transform:uppercase;font-family:IBM Plex Mono,monospace;"
                        f"margin-bottom:8px;font-weight:700'>{cat}</div>"
                    )
                    for m in markets:
                        yes_pct   = m["yes_prob"] * 100
                        liq_fmt   = f"${m['liquidity']:,.0f}" if m["liquidity"] >= 1000 else f"${m['liquidity']:.0f}"
                        bar_color = "#f85149" if yes_pct >= 50 else "#e3b341" if yes_pct >= 25 else "#3fb950"
                        short_q   = m["question"][:62] + ("..." if len(m["question"]) > 62 else "")
                        part += (
                            f"<div style='background:#161b22;border:1px solid #30363d;"
                            f"border-radius:5px;padding:10px 12px;margin-bottom:6px'>"
                            f"<div style='font-size:11px;color:#c9d1d9;margin-bottom:6px;line-height:1.3'>"
                            f"<a href='{m['url']}' target='_blank' style='color:#c9d1d9;text-decoration:none'>"
                            f"{short_q}</a></div>"
                            f"<div style='display:flex;align-items:center;gap:8px'>"
                            f"<div style='flex:1;background:#21262d;border-radius:3px;height:6px'>"
                            f"<div style='background:{bar_color};width:{yes_pct:.0f}%;height:6px;"
                            f"border-radius:3px'></div></div>"
                            f"<span style='font-family:IBM Plex Mono,monospace;font-size:12px;"
                            f"font-weight:700;color:{bar_color};min-width:38px'>{yes_pct:.0f}%</span>"
                            f"<span style='font-size:9px;color:#8b949e;font-family:IBM Plex Mono,monospace'>"
                            f"liq {liq_fmt} · {m['end_date']}</span>"
                            f"</div></div>"
                        )
                    part += "</div>"
                    poly_parts.append(part)

                n_cols = min(len(poly_parts), 2)
                if n_cols > 0:
                    pcols = st.columns(n_cols)
                    for i, part in enumerate(poly_parts):
                        with pcols[i % n_cols]:
                            st.html(part)
                st.caption("Real-money prediction markets · Polymarket · 30-min cache")

    with trend_col:
        with st.expander("📈 Trending Topics — Live Frequency", expanded=True):
            topics = _trending_topics(news)
            if not topics:
                st.caption("Not enough recent articles to detect trends.")
            else:
                max_count = max(t["count"] for t in topics) or 1
                trend_html = ""
                for i, t in enumerate(topics):
                    color = _TOPIC_COLORS.get(t["topic"], "#94a3b8")
                    pct   = t["count"] / max_count * 100
                    icon  = "🔥" if i == 0 else ("⚡" if i == 1 else "")
                    trend_html += (
                        f"<div style='margin-bottom:12px'>"
                        f"<div style='display:flex;justify-content:space-between;"
                        f"font-family:IBM Plex Mono,monospace;font-size:11px;margin-bottom:4px'>"
                        f"<span style='color:{color}'>{icon} {t['topic']}</span>"
                        f"<span style='color:#8b949e'>{t['count']}</span></div>"
                        f"<div style='background:#21262d;border-radius:3px;height:5px'>"
                        f"<div style='background:{color};width:{pct:.0f}%;height:5px;"
                        f"border-radius:3px'></div></div>"
                        f"</div>"
                    )
                since = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%H:%M UTC")
                st.html(trend_html)
                st.caption(f"Keyword frequency · all live sources · since {since}")

    # ── Filters ───────────────────────────────────────────────────────────────
    st.divider()
    f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
    with f1:
        ticker_options = ["All"] + sorted(portfolio_tickers)
        sel_idx = st.selectbox(
            "Filter by ticker",
            range(len(ticker_options)),
            format_func=lambda i: (
                "All Tickers" if ticker_options[i] == "All"
                else f"{ticker_options[i]} — {ASSETS.get(ticker_options[i], {}).get('name', '')}"
            ),
        )
        selected_ticker = ticker_options[sel_idx]
    with f2:
        sentiment_filter = st.selectbox("Sentiment", ["All", "BEARISH", "BULLISH", "NEUTRAL"])
    with f3:
        geo_filter = st.selectbox("Type", ["All", "Geo-Risk", "General"])
    with f4:
        limit = st.selectbox("Articles", [25, 50, 100], index=1)

    if news.is_empty():
        st.info("No news found. APIs may be rate-limited or market is closed.")
        return

    # ── Source chips ──────────────────────────────────────────────────────────
    n_alpaca  = len(alpaca_news)  if not alpaca_news.is_empty()  else 0
    n_finnhub = len(finnhub_news) if not finnhub_news.is_empty() else 0
    n_wsj     = len(wsj_news)     if not wsj_news.is_empty()     else 0
    st.html(
        f"<div style='margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap'>"
        f"<span style='background:#21262d;border:1px solid #30363d;border-radius:4px;"
        f"padding:3px 10px;font-family:IBM Plex Mono,monospace;font-size:10px;color:#58a6ff'>"
        f"ALPACA &nbsp;{n_alpaca}</span>"
        f"<span style='background:#21262d;border:1px solid #30363d;border-radius:4px;"
        f"padding:3px 10px;font-family:IBM Plex Mono,monospace;font-size:10px;color:#e3b341'>"
        f"FINNHUB &nbsp;{n_finnhub}</span>"
        f"<span style='background:#21262d;border:1px solid #30363d;border-radius:4px;"
        f"padding:3px 10px;font-family:IBM Plex Mono,monospace;font-size:10px;color:#a371f7'>"
        f"WSJ/MW &nbsp;{n_wsj}</span>"
        f"<span style='background:#21262d;border:1px solid #30363d;border-radius:4px;"
        f"padding:3px 10px;font-family:IBM Plex Mono,monospace;font-size:10px;color:#00FFB2'>"
        f"TOTAL &nbsp;{len(news)}</span>"
        f"</div>"
    )

    # ── Build article cards ───────────────────────────────────────────────────
    sentiment_counts: dict[str, int] = {"BEARISH": 0, "BULLISH": 0, "NEUTRAL": 0}
    ticker_counts:    dict[str, int] = {}
    geo_count  = 0
    cards_html: list[str] = []
    shown      = 0

    for row in news.to_dicts():
        if shown >= limit:
            break

        headline     = row.get("headline",     "")
        summary      = row.get("summary",      "")
        source       = row.get("source",       "")
        published_at = row.get("published_at", "")
        tickers_str  = row.get("tickers",      "") or ""
        feed         = row.get("feed",         "alpaca")
        url          = row.get("url",          "#")

        _, badge_label = _sentiment(headline, summary)
        is_geo   = _is_geo(headline, summary)
        breaking = _is_breaking(published_at)

        # Filters
        if selected_ticker != "All":
            art_tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
            if selected_ticker not in art_tickers:
                continue
        if sentiment_filter != "All" and badge_label != sentiment_filter:
            continue
        if geo_filter == "Geo-Risk" and not is_geo:
            continue
        if geo_filter == "General" and is_geo:
            continue

        sentiment_counts[badge_label] += 1
        if is_geo:
            geo_count += 1

        art_tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
        for t in art_tickers:
            ticker_counts[t] = ticker_counts.get(t, 0) + 1

        fg, bg, border = SENTIMENT_COLORS[badge_label]

        tkr_spans = "".join(
            f"<span style='display:inline-block;padding:1px 5px;background:#21262d;"
            f"border:1px solid #30363d;border-radius:3px;font-size:10px;font-weight:700;"
            f"color:#00FFB2;font-family:IBM Plex Mono,monospace;margin-right:3px'>{t}</span>"
            for t in art_tickers[:4]
        )
        geo_span = (
            "<span style='display:inline-block;padding:2px 6px;border-radius:3px;"
            "font-size:9px;font-weight:700;background:#58a6ff18;color:#58a6ff;"
            "border:1px solid #58a6ff40;margin-right:4px;font-family:IBM Plex Mono,monospace'>"
            "GEO&#8209;RISK</span>"
        ) if is_geo else ""

        breaking_span = (
            "<span style='display:inline-block;padding:2px 6px;border-radius:3px;"
            "font-size:9px;font-weight:700;background:#f8514920;color:#f85149;"
            "border:1px solid #f8514960;margin-right:4px;font-family:IBM Plex Mono,monospace'>"
            "⚡ BREAKING</span>"
        ) if breaking else ""

        if feed == "wsj":
            feed_color, feed_lbl = "#a371f7", "WSJ/MW"
        elif feed == "finnhub":
            feed_color, feed_lbl = "#e3b341", "FINNHUB"
        else:
            feed_color, feed_lbl = "#58a6ff", "ALPACA"

        card_border = "#f8514960" if breaking else "#30363d"
        safe_title  = headline.replace("<", "&lt;").replace(">", "&gt;")
        safe_url    = url if isinstance(url, str) and url.startswith("http") else "#"

        cards_html.append(
            f"<div style='background:#161b22;border:1px solid {card_border};border-radius:6px;"
            f"padding:12px 16px;margin-bottom:8px'>"
            f"<div style='display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:6px'>"
            f"{breaking_span}"
            f"<span style='display:inline-block;padding:2px 7px;border-radius:3px;font-size:9px;"
            f"font-weight:700;font-family:IBM Plex Mono,monospace;letter-spacing:0.5px;"
            f"background:{bg};color:{fg};border:1px solid {border}'>{badge_label}</span>"
            f"{geo_span}{tkr_spans}"
            f"<span style='margin-left:auto;font-size:9px;color:{feed_color};"
            f"font-family:IBM Plex Mono,monospace;letter-spacing:0.8px'>{feed_lbl}</span>"
            f"</div>"
            f"<div style='font-size:13px;font-weight:500;color:#c9d1d9;line-height:1.4;margin:4px 0'>"
            f"<a href='{safe_url}' target='_blank' style='color:#c9d1d9;text-decoration:none'>"
            f"{safe_title}</a></div>"
            f"<div style='font-size:11px;color:#8b949e;font-family:IBM Plex Mono,monospace;margin-top:5px'>"
            f"{_source_display(source)} &nbsp;·&nbsp; {_time_ago(published_at)}</div>"
            f"</div>"
        )
        shown += 1

    # ── Feed + stats layout ───────────────────────────────────────────────────
    col_feed, col_stats = st.columns([3, 1])

    with col_feed:
        if cards_html:
            st.html("<div>" + "".join(cards_html) + "</div>")
        else:
            st.info("No articles match the selected filters.")

    with col_stats:
        total = max(sum(sentiment_counts.values()), 1)
        sent_html = (
            "<div style='font-size:9px;color:#8b949e;letter-spacing:1.2px;"
            "text-transform:uppercase;margin-bottom:10px'>Sentiment</div>"
        )
        for label, count in sentiment_counts.items():
            color = "#f85149" if label == "BEARISH" else "#3fb950" if label == "BULLISH" else "#e3b341"
            pct   = count / total * 100
            sent_html += (
                f"<div style='margin-bottom:10px'>"
                f"<div style='display:flex;justify-content:space-between;"
                f"font-family:IBM Plex Mono,monospace;font-size:11px;margin-bottom:3px'>"
                f"<span style='color:{color}'>{label}</span>"
                f"<span style='color:#8b949e'>{count}</span></div>"
                f"<div style='background:#21262d;border-radius:2px;height:4px'>"
                f"<div style='background:{color};width:{pct:.0f}%;height:4px;border-radius:2px'>"
                f"</div></div></div>"
            )
        st.html(sent_html)

        sidebar_html = (
            f"<div style='background:#58a6ff15;border:1px solid #58a6ff30;border-radius:4px;"
            f"padding:8px 10px;margin:12px 0;font-family:IBM Plex Mono,monospace'>"
            f"<div style='font-size:9px;color:#8b949e;letter-spacing:1px'>GEO-RISK</div>"
            f"<div style='font-size:18px;font-weight:700;color:#58a6ff'>{geo_count}</div></div>"
        )
        if ticker_counts:
            top = sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:6]
            max_c = max(c for _, c in top)
            sidebar_html += (
                "<hr style='border-color:#30363d;margin:10px 0'/>"
                "<div style='font-size:9px;color:#8b949e;letter-spacing:1.2px;"
                "text-transform:uppercase;margin-bottom:10px'>Most Mentioned</div>"
            )
            for tkr, count in top:
                pct = count / max_c * 100
                sidebar_html += (
                    f"<div style='margin-bottom:8px'>"
                    f"<div style='display:flex;justify-content:space-between;"
                    f"font-family:IBM Plex Mono,monospace;font-size:11px;margin-bottom:2px'>"
                    f"<span style='color:#00FFB2'>{tkr}</span>"
                    f"<span style='color:#8b949e'>{count}</span></div>"
                    f"<div style='background:#21262d;border-radius:2px;height:3px'>"
                    f"<div style='background:#00FFB2;width:{pct:.0f}%;height:3px;border-radius:2px'>"
                    f"</div></div></div>"
                )
        sidebar_html += (
            f"<hr style='border-color:#30363d;margin:10px 0'/>"
            f"<div style='font-family:IBM Plex Mono,monospace;font-size:10px;color:#8b949e'>"
            f"{shown} articles · {geo_count} geo-risk</div>"
        )
        st.html(sidebar_html)

        st.html(
            "<div style='margin-top:10px'>"
            "<div style='font-size:9px;color:#8b949e;letter-spacing:1.2px;"
            "text-transform:uppercase;margin-bottom:6px'>Sources</div>"
            "<span style='background:#21262d;border:1px solid #30363d;border-radius:4px;"
            "padding:3px 8px;font-family:IBM Plex Mono,monospace;font-size:10px;"
            "color:#58a6ff;margin-right:4px'>ALPACA</span>"
            "<span style='background:#21262d;border:1px solid #30363d;border-radius:4px;"
            "padding:3px 8px;font-family:IBM Plex Mono,monospace;font-size:10px;"
            "color:#e3b341;margin-right:4px'>FINNHUB</span>"
            "<span style='background:#21262d;border:1px solid #30363d;border-radius:4px;"
            "padding:3px 8px;font-family:IBM Plex Mono,monospace;font-size:10px;"
            "color:#a371f7'>WSJ/MW</span>"
            "</div>"
        )


def _render_macro_panel() -> None:
    """
    Compact live macro indicators panel — rendered above the news feed.
    Uses FRED API if key is configured; shows placeholder cards otherwise.
    12-month yield curve sparkline rendered inline.
    """
    with st.expander("📊 Live Macro Indicators (FRED)", expanded=True):
        if not FRED_API_KEY:
            st.caption(
                "Add `FRED_API_KEY` to your `.env` to enable live FRED indicators. "
                "Free key at fred.stlouisfed.org."
            )
            return

        # 5 live FRED metrics in one row
        cols = st.columns(5)
        for i, (sid, meta) in enumerate(_FRED_SERIES.items()):
            val, delta = _fetch_fred_indicator(sid)
            with cols[i]:
                label = meta["label"]
                unit  = meta["unit"]
                if val is not None:
                    val_str = f"{val:.2f}" if unit in ("%", "idx") else f"${val:.1f}"
                    if meta["invert_risk"]:
                        color = "#f85149" if val < 0 else "#3fb950"
                    else:
                        color = "#c9d1d9"
                    delta_html = ""
                    if delta is not None:
                        dc = "#3fb950" if delta >= 0 else "#f85149"
                        delta_html = (
                            f"<div style='font-size:10px;color:{dc};"
                            f"font-family:IBM Plex Mono,monospace'>{delta:+.2f}</div>"
                        )
                    st.markdown(
                        f"<div style='background:#161b22;border:1px solid #30363d;"
                        f"border-radius:6px;padding:10px;text-align:center'>"
                        f"<div style='font-size:9px;color:#8b949e;letter-spacing:1px'>"
                        f"{label.upper()}</div>"
                        f"<div style='font-size:20px;font-weight:700;color:{color};"
                        f"font-family:IBM Plex Mono,monospace'>{val_str}"
                        f"<span style='font-size:10px;color:#8b949e'> {unit}</span></div>"
                        f"{delta_html}</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"<div style='background:#161b22;border:1px solid #30363d;"
                        f"border-radius:6px;padding:10px;text-align:center'>"
                        f"<div style='font-size:9px;color:#8b949e;letter-spacing:1px'>"
                        f"{label.upper()}</div>"
                        f"<div style='font-size:16px;color:#8b949e'>—</div></div>",
                        unsafe_allow_html=True,
                    )

        # Yield curve sparkline
        yc_df = _fetch_yield_curve_series()
        if not yc_df.is_empty():
            vals  = yc_df["value"].to_list()
            dates = yc_df["date"].to_list()
            is_inverted = vals[-1] < 0 if vals else False
            fig = go.Figure(go.Scatter(
                x=dates, y=vals, mode="lines",
                line=dict(color="#f85149" if is_inverted else "#3fb950", width=1.5),
                fill="tozeroy",
                fillcolor="rgba(248,81,73,0.07)" if is_inverted else "rgba(63,185,80,0.07)",
                hovertemplate="%{x|%Y-%m-%d}: %{y:.2f}%<extra></extra>",
            ))
            fig.add_hline(y=0, line_dash="dash", line_color="#8b949e",
                          annotation_text="Inversion threshold",
                          annotation_font=dict(color="#8b949e", size=9))
            fig = set_dark_theme(fig)
            fig.update_layout(
                height=120, showlegend=False,
                margin=dict(l=0, r=0, t=8, b=0),
                title=dict(
                    text="10Y–2Y Yield Curve (12M) · "
                         f"{'⚠ INVERTED' if is_inverted else 'NORMAL'}",
                    font=dict(size=10, color="#f85149" if is_inverted else "#3fb950"),
                    x=0,
                ),
            )
            st.plotly_chart(fig, use_container_width=True)
        st.caption("FRED live data · 30-min cache · Inversion = recession warning signal")


# ── Main render entry point ───────────────────────────────────────────────────

def render(demo_mode: bool = True) -> None:
    """Render the Live Intelligence Feed tab."""

    # Static header — never reruns unless the whole page does
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        st.markdown("### Live Intelligence Feed")
        st.caption(
            "Alpaca · Finnhub (Reuters / AP / CNBC) · WSJ / MarketWatch RSS · "
            "Polymarket · FRED Macro · **auto-refresh every 2 min** via st.fragment"
        )
    with col_refresh:
        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
        if st.button("↻ Refresh now", type="secondary"):
            fetch_alpaca_news.clear()
            fetch_finnhub_news.clear()
            fetch_wsj_rss.clear()
            fetch_polymarket_geo.clear()
            _fetch_fred_indicator.clear()
            _fetch_yield_curve_series.clear()
            st.rerun()

    # Live macro indicators panel (FRED — 30-min cache, static section)
    _render_macro_panel()

    st.divider()

    # Live fragment — only this block reruns every 2 min
    _live_feed_fragment(demo_mode=demo_mode)
