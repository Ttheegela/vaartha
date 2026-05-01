"""
tab6_news.py — Live Intelligence Feed
Dual-source news: Alpaca (Benzinga/PRN) + Finnhub (Reuters/AP/MarketWatch/CNBC).
Sentiment scoring, geo-risk tagging, source badges, auto-refresh.
"""

import polars as pl
import streamlit as st
from datetime import datetime, timezone
from src.data.fetchers import fetch_alpaca_news, fetch_finnhub_news, fetch_alpaca_portfolio, fetch_polymarket_geo
from config import TICKERS, ASSETS

# ── Geo-risk keywords for tagging ────────────────────────────────────────────
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

# Trusted source display names
_SOURCE_DISPLAY = {
    "benzinga":           "Benzinga",
    "finnhub":            "Finnhub",
    "reuters":            "Reuters",
    "ap":                 "AP News",
    "marketwatch":        "MarketWatch",
    "cnbc":               "CNBC",
    "bloomberg":          "Bloomberg",
    "globenewswire":      "Globe Newswire",
    "prnewswire":         "PR Newswire",
    "seekingalpha":       "Seeking Alpha",
    "thestreet":          "TheStreet",
    "investopedia":       "Investopedia",
}


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


def _merge_sources(alpaca: pl.DataFrame, finnhub: pl.DataFrame) -> pl.DataFrame:
    """Merge and deduplicate Alpaca + Finnhub news by headline."""
    frames = []
    if not alpaca.is_empty():
        frames.append(alpaca.with_columns(pl.lit("alpaca").alias("feed")))
    if not finnhub.is_empty():
        frames.append(finnhub.with_columns(pl.lit("finnhub").alias("feed")))
    if not frames:
        return pl.DataFrame()

    combined = pl.concat(frames, how="diagonal_relaxed")

    # Deduplicate: normalise headline to lower-stripped, keep first occurrence
    combined = (
        combined
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


def render(demo_mode: bool = True) -> None:
    """Render the Live Intelligence Feed tab."""

    # ── Header ────────────────────────────────────────────────────────────────
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        st.markdown("### Live Intelligence Feed")
        st.caption("Alpaca News · Finnhub (Reuters / AP / MarketWatch) · Polymarket signals · updates every 15 min")
    with col_refresh:
        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
        if st.button("↻ Refresh", type="secondary"):
            fetch_alpaca_news.clear()
            fetch_finnhub_news.clear()
            fetch_polymarket_geo.clear()
            st.rerun()

    # ── Polymarket Geo-Risk Panel ─────────────────────────────────────────────
    with st.expander("🔮 Polymarket — Crowd-Sourced Geopolitical Probabilities", expanded=True):
        with st.spinner("Loading Polymarket signals..."):
            poly_df = fetch_polymarket_geo(max_markets=8)
        if poly_df.is_empty():
            st.caption("Polymarket data unavailable — check connection.")
        else:
            _cat_color = {
                "China / Taiwan":  "#f85149",
                "Iran":            "#e3b341",
                "Russia / Ukraine":"#58a6ff",
                "US Macro":        "#a371f7",
                "Geopolitical":    "#00FFB2",
            }
            # Group by category
            cats = poly_df["category"].unique().to_list()
            cols_poly = st.columns(min(len(cats), 3))
            cat_chunks: dict[str, list] = {}
            for row in poly_df.to_dicts():
                cat_chunks.setdefault(row["category"], []).append(row)

            poly_html_parts = []
            for cat, markets in sorted(cat_chunks.items()):
                color = _cat_color.get(cat, "#00FFB2")
                part = (
                    f"<div style='margin-bottom:16px'>"
                    f"<div style='font-size:9px;color:{color};letter-spacing:1.5px;"
                    f"text-transform:uppercase;font-family:IBM Plex Mono,monospace;"
                    f"margin-bottom:8px;font-weight:700'>{cat}</div>"
                )
                for m in markets:
                    yes_pct  = m["yes_prob"] * 100
                    liq_fmt  = f"${m['liquidity']:,.0f}" if m["liquidity"] >= 1000 else f"${m['liquidity']:.0f}"
                    bar_color = "#f85149" if yes_pct >= 50 else "#e3b341" if yes_pct >= 25 else "#3fb950"
                    short_q  = m["question"]
                    if len(short_q) > 62:
                        short_q = short_q[:59] + "..."
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
                poly_html_parts.append(part)

            # Render in columns
            n_cols = min(len(poly_html_parts), 3)
            if n_cols > 0:
                pcols = st.columns(n_cols)
                for i, part in enumerate(poly_html_parts):
                    with pcols[i % n_cols]:
                        st.html(part)

            st.caption("Real-money prediction markets · Powered by Polymarket · 30-min cache")

    # ── Portfolio tickers ─────────────────────────────────────────────────────
    positions = fetch_alpaca_portfolio()
    portfolio_tickers = positions["ticker"].to_list() if not positions.is_empty() else TICKERS

    # ── Filter row ────────────────────────────────────────────────────────────
    f1, f2, f3, f4 = st.columns([2, 1, 1, 1])

    with f1:
        ticker_options = ["All"] + sorted(portfolio_tickers)

        def _tkr_label(t: str) -> str:
            if t == "All":
                return "All Tickers"
            name = ASSETS.get(t, {}).get("name", "")
            return f"{t} — {name}" if name else t

        sel_idx = st.selectbox(
            "Filter by ticker",
            range(len(ticker_options)),
            format_func=lambda i: _tkr_label(ticker_options[i]),
        )
        selected_ticker = ticker_options[sel_idx]

    with f2:
        sentiment_filter = st.selectbox("Sentiment", ["All", "BEARISH", "BULLISH", "NEUTRAL"])
    with f3:
        geo_filter = st.selectbox("Type", ["All", "Geo-Risk", "General"])
    with f4:
        limit = st.selectbox("Articles", [25, 50, 100], index=1)

    st.divider()

    # ── Fetch from both sources ───────────────────────────────────────────────
    # Fall back to full TICKERS universe when portfolio is empty or "All" is selected
    tickers_to_fetch = (
        [selected_ticker] if selected_ticker != "All"
        else (sorted(portfolio_tickers) if portfolio_tickers else TICKERS)
    )

    with st.spinner("Loading intelligence feed..."):
        alpaca_news  = fetch_alpaca_news(tickers=tickers_to_fetch, limit=limit)
        finnhub_news = fetch_finnhub_news(tickers=tickers_to_fetch, limit=30)
        news = _merge_sources(alpaca_news, finnhub_news)

    if news is None or news.is_empty():
        st.info("No news found. APIs may be rate-limited or market is closed.")
        return

    # ── Source summary chips ──────────────────────────────────────────────────
    n_alpaca  = len(alpaca_news)  if not alpaca_news.is_empty()  else 0
    n_finnhub = len(finnhub_news) if not finnhub_news.is_empty() else 0
    st.html(
        f"<div style='margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap'>"
        f"<span style='background:#21262d;border:1px solid #30363d;border-radius:4px;"
        f"padding:3px 10px;font-family:IBM Plex Mono,monospace;font-size:10px;color:#58a6ff'>"
        f"ALPACA &nbsp; {n_alpaca}</span>"
        f"<span style='background:#21262d;border:1px solid #30363d;border-radius:4px;"
        f"padding:3px 10px;font-family:IBM Plex Mono,monospace;font-size:10px;color:#e3b341'>"
        f"FINNHUB  {n_finnhub}</span>"
        f"<span style='background:#21262d;border:1px solid #30363d;border-radius:4px;"
        f"padding:3px 10px;font-family:IBM Plex Mono,monospace;font-size:10px;color:#00FFB2'>"
        f"TOTAL  {len(news)}</span>"
        f"</div>"
    )

    # ── Pre-process all articles, collect stats ───────────────────────────────
    sentiment_counts = {"BEARISH": 0, "BULLISH": 0, "NEUTRAL": 0}
    ticker_counts:  dict[str, int] = {}
    geo_count  = 0
    cards_html = []

    SENTIMENT_COLORS = {
        "BEARISH": ("#f85149", "#f8514918", "#f8514940"),
        "BULLISH": ("#3fb950", "#3fb95018", "#3fb95040"),
        "NEUTRAL": ("#e3b341", "#e3b34118", "#e3b34140"),
    }

    for row in news.to_dicts():
        headline     = row.get("headline", "")
        summary      = row.get("summary",  "")
        source       = row.get("source",   "")
        published_at = row.get("published_at", "")
        tickers_str  = row.get("tickers", "")
        feed         = row.get("feed", "alpaca")
        url          = row.get("url", "#")

        _, badge_label = _sentiment(headline, summary)
        is_geo = _is_geo(headline, summary)

        if sentiment_filter != "All" and badge_label != sentiment_filter:
            continue
        if geo_filter == "Geo-Risk" and not is_geo:
            continue
        if geo_filter == "General" and is_geo:
            continue

        sentiment_counts[badge_label] += 1
        if is_geo:
            geo_count += 1

        article_tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
        for t in article_tickers:
            ticker_counts[t] = ticker_counts.get(t, 0) + 1

        fg, bg, border = SENTIMENT_COLORS[badge_label]
        tkr_spans = "".join(
            f"<span style='display:inline-block;padding:1px 5px;background:#21262d;"
            f"border:1px solid #30363d;border-radius:3px;font-size:10px;font-weight:700;"
            f"color:#00FFB2;font-family:IBM Plex Mono,monospace;margin-right:3px'>{t}</span>"
            for t in article_tickers[:4]
        )
        geo_span = (
            "<span style='display:inline-block;padding:2px 6px;border-radius:3px;"
            "font-size:9px;font-weight:700;background:#58a6ff18;color:#58a6ff;"
            "border:1px solid #58a6ff40;margin-right:4px;font-family:IBM Plex Mono,monospace'>"
            "GEO&#8209;RISK</span>"
        ) if is_geo else ""

        feed_color = "#58a6ff" if feed == "alpaca" else "#e3b341"
        feed_lbl   = "ALPACA" if feed == "alpaca" else "FINNHUB"
        src_disp   = _source_display(source)
        time_str   = _time_ago(published_at)
        safe_title = headline.replace("<", "&lt;").replace(">", "&gt;")
        safe_url   = url if url.startswith("http") else "#"

        cards_html.append(
            f"<div style='background:#161b22;border:1px solid #30363d;border-radius:6px;"
            f"padding:12px 16px;margin-bottom:8px'>"
            f"<div style='display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:6px'>"
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
            f"{src_disp} &nbsp;·&nbsp; {time_str}</div>"
            f"</div>"
        )

    rendered = len(cards_html)

    # ── Layout: feed + stats sidebar ─────────────────────────────────────────
    col_feed, col_stats = st.columns([3, 1])

    with col_feed:
        if cards_html:
            st.html("<div>" + "".join(cards_html) + "</div>")
        else:
            st.info("No articles match the selected filters.")

    # ── Stats sidebar ─────────────────────────────────────────────────────────
    with col_stats:
        total = max(sum(sentiment_counts.values()), 1)
        sent_html = "<div style='font-size:9px;color:#8b949e;letter-spacing:1.2px;text-transform:uppercase;margin-bottom:10px'>Sentiment</div>"
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
                f"<div style='background:{color};width:{pct:.0f}%;height:4px;border-radius:2px'></div>"
                f"</div></div>"
            )
        st.html(sent_html)

        # Build geo + mentions sidebar as single html block
        sidebar_html = (
            f"<div style='background:#58a6ff15;border:1px solid #58a6ff30;border-radius:4px;"
            f"padding:8px 10px;margin:12px 0;font-family:IBM Plex Mono,monospace'>"
            f"<div style='font-size:9px;color:#8b949e;letter-spacing:1px'>GEO-RISK ARTICLES</div>"
            f"<div style='font-size:18px;font-weight:700;color:#58a6ff'>{geo_count}</div></div>"
        )
        if ticker_counts:
            top = sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:6]
            max_count = max(c for _, c in top) if top else 1
            sidebar_html += (
                "<hr style='border-color:#30363d;margin:10px 0'/>"
                "<div style='font-size:9px;color:#8b949e;letter-spacing:1.2px;"
                "text-transform:uppercase;margin-bottom:10px'>Most Mentioned</div>"
            )
            for tkr, count in top:
                pct = count / max_count * 100
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
            f"{rendered} articles &nbsp;·&nbsp; {geo_count} geo-risk</div>"
        )
        st.html(sidebar_html)

        # Source chips
        source_html = (
            f"<div style='margin-top:10px'>"
            f"<div style='font-size:9px;color:#8b949e;letter-spacing:1.2px;"
            f"text-transform:uppercase;margin-bottom:6px'>Sources</div>"
            f"<span style='background:#21262d;border:1px solid #30363d;border-radius:4px;"
            f"padding:3px 8px;font-family:IBM Plex Mono,monospace;font-size:10px;color:#58a6ff;"
            f"margin-right:4px'>ALPACA</span>"
            f"<span style='background:#21262d;border:1px solid #30363d;border-radius:4px;"
            f"padding:3px 8px;font-family:IBM Plex Mono,monospace;font-size:10px;color:#e3b341'>"
            f"FINNHUB</span></div>"
        )
        st.html(source_html)
