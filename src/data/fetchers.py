"""
fetchers.py — GeoSentinel Terminal (VARTA)
Live data fetchers: Alpaca portfolio, Alpaca news, yfinance prices.
All functions are cached via @st.cache_data — tabs never call these directly,
they go through loaders.py instead.
"""

import polars as pl
import yfinance as yf
import requests
import streamlit as st
from datetime import datetime, timedelta
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from src.utils import log
from config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER,
    FINNHUB_API_KEY, TICKERS, TICKER_QUERY_TERMS,
)


# ── Alpaca Client Singleton ───────────────────────────────────────────────────

def get_trading_client() -> TradingClient:
    """
    Return authenticated Alpaca TradingClient (paper mode always).

    Returns:
        TradingClient instance.
    Example:
        client = get_trading_client()
    """
    return TradingClient(
        api_key=ALPACA_API_KEY,
        secret_key=ALPACA_SECRET_KEY,
        paper=ALPACA_PAPER,
    )


def get_data_client() -> StockHistoricalDataClient:
    """
    Return Alpaca StockHistoricalDataClient for market data.

    Returns:
        StockHistoricalDataClient instance.
    Example:
        client = get_data_client()
    """
    return StockHistoricalDataClient(
        api_key=ALPACA_API_KEY,
        secret_key=ALPACA_SECRET_KEY,
    )


# ── Alpaca Portfolio ──────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def fetch_alpaca_portfolio() -> pl.DataFrame:
    """
    Fetch open positions from Alpaca paper account.

    Returns:
        DataFrame with columns: ticker, qty, avg_entry_price, current_price,
        market_value, unrealized_pl, unrealized_plpc, side
    Example:
        df = fetch_alpaca_portfolio()
    """
    try:
        client = get_trading_client()
        positions = client.get_all_positions()
        if not positions:
            log.warning("No open positions in Alpaca paper account")
            return pl.DataFrame()

        rows = []
        for p in positions:
            rows.append({
                "ticker":           p.symbol,
                "qty":              float(p.qty),
                "avg_entry_price":  float(p.avg_entry_price),
                "current_price":    float(p.current_price),
                "market_value":     float(p.market_value),
                "unrealized_pl":    float(p.unrealized_pl),
                "unrealized_plpc":  float(p.unrealized_plpc) * 100,
                "side":             str(p.side.value),
            })
        return pl.DataFrame(rows)

    except Exception as e:
        log.error(f"Alpaca portfolio fetch failed: {e}")
        return pl.DataFrame()


@st.cache_data(ttl=60)
def fetch_alpaca_account() -> dict:
    """
    Fetch Alpaca paper account summary.

    Returns:
        Dict with keys: portfolio_value, cash, buying_power, equity, day_pl, day_pl_pct
    Example:
        acct = fetch_alpaca_account()
    """
    try:
        client = get_trading_client()
        acct = client.get_account()
        return {
            "portfolio_value": float(acct.portfolio_value),
            "cash":            float(acct.cash),
            "buying_power":    float(acct.buying_power),
            "equity":          float(acct.equity),
            "day_pl":          float(acct.equity) - float(acct.last_equity),
            "day_pl_pct":      ((float(acct.equity) - float(acct.last_equity))
                                / float(acct.last_equity) * 100)
                               if float(acct.last_equity) > 0 else 0.0,
        }
    except Exception as e:
        log.error(f"Alpaca account fetch failed: {e}")
        return {}


# ── Alpaca News ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=900)
def fetch_alpaca_news(tickers: list[str] | None = None, limit: int = 50) -> pl.DataFrame:
    """
    Fetch latest news from Alpaca News API filtered to given tickers.
    Falls back to all VARTA tickers if none provided.
    Cached for 15 minutes.

    Args:
        tickers: List of ticker symbols to filter news by.
        limit: Max articles to return (default 50).
    Returns:
        DataFrame with columns: headline, summary, url, source, published_at, tickers
    Example:
        df = fetch_alpaca_news(tickers=["NVDA", "TSM"])
    """
    if not ALPACA_API_KEY:
        log.warning("Alpaca API key missing — skipping news fetch")
        return pl.DataFrame()

    symbols = tickers or TICKERS
    symbols_str = ",".join(symbols)

    url = "https://data.alpaca.markets/v1beta1/news"
    headers = {
        "APCA-API-KEY-ID":     ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
    }
    params = {
        "symbols": symbols_str,
        "limit":   limit,
        "sort":    "desc",
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        articles = resp.json().get("news", [])

        if not articles:
            return pl.DataFrame()

        rows = []
        for a in articles:
            rows.append({
                "headline":     a.get("headline", ""),
                "summary":      a.get("summary", ""),
                "url":          a.get("url", ""),
                "source":       a.get("source", ""),
                "published_at": a.get("created_at", ""),
                "tickers":      ",".join(a.get("symbols", [])),
            })
        return pl.DataFrame(rows).with_columns(
            pl.col("published_at").str.to_datetime(
                format="%Y-%m-%dT%H:%M:%SZ", strict=False,
                time_unit="us", time_zone="UTC",
            )
        )

    except Exception as e:
        log.error(f"Alpaca news fetch failed: {e}")
        return pl.DataFrame()


# ── yfinance Live Prices ──────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def fetch_live_prices(tickers: list[str]) -> pl.DataFrame:
    """
    Fetch current-day OHLCV prices for a list of tickers via yfinance.
    Cached for 60 seconds.

    Args:
        tickers: List of ticker symbols.
    Returns:
        DataFrame with columns: ticker, date, open, high, low, close, volume, return_1d
    Example:
        df = fetch_live_prices(["NVDA", "GLD", "TSM"])
    """
    try:
        rows = []
        for tkr in tickers:
            try:
                raw = yf.download(tkr, period="5d", interval="1d",
                                  auto_adjust=True, progress=False,
                                  multi_level_index=False)
                if raw.empty:
                    continue
                closes = raw["Close"].tolist()
                for i, (idx, row) in enumerate(raw.iterrows()):
                    ret = (closes[i] / closes[i - 1] - 1) if i > 0 else 0.0
                    rows.append({
                        "ticker":    tkr,
                        "date":      idx.date(),
                        "open":      float(row["Open"]),
                        "high":      float(row["High"]),
                        "low":       float(row["Low"]),
                        "close":     float(row["Close"]),
                        "volume":    float(row["Volume"]),
                        "return_1d": float(ret),
                    })
            except Exception:
                continue
        if not rows:
            return pl.DataFrame()
        return pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Date))

    except Exception as e:
        log.error(f"yfinance live price fetch failed: {e}")
        return pl.DataFrame()


# ── Polymarket Geo-Risk Signals ───────────────────────────────────────────────

# Curated list of VARTA-relevant Polymarket market IDs / question keywords.
# These are real-money prediction markets directly tied to the 14 VARTA events.
_POLY_GEO_KEYWORDS = [
    "taiwan", "iran", "ukraine", "ceasefire", "russia invade",
    "china blockade", "us invade", "nuclear deal", "us recession",
    "china invad", "nato", "iranian regime",
]
_POLY_EXCLUDE = [
    "fifa", "world cup", "nhl", "nba", "nfl", "mlb", "super bowl",
    "oscar", "grammy", "bitcoin", "crypto", "election", "senator",
    "governor", "nominee", "primary",
]


@st.cache_data(ttl=1800)   # 30-min cache — prediction markets move slowly
def fetch_polymarket_geo(max_markets: int = 10) -> pl.DataFrame:
    """
    Fetch active geopolitical prediction markets from Polymarket Gamma API.
    No API key required — public endpoint.
    Returns top markets by liquidity relevant to VARTA thesis events.

    Args:
        max_markets: Maximum number of markets to return (default 10).
    Returns:
        DataFrame with columns: question, yes_prob, no_prob, liquidity,
                                end_date, url, category
    Example:
        df = fetch_polymarket_geo()
        # question='Will China invade Taiwan...' yes_prob=0.07 liquidity=979681
    """
    all_markets: list[dict] = []
    try:
        for offset in [0, 500, 1000]:
            resp = requests.get(
                "https://gamma-api.polymarket.com/markets",
                params={"active": "true", "limit": 500, "offset": offset},
                timeout=10,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            all_markets.extend(batch)
    except Exception as e:
        log.error(f"Polymarket fetch failed: {e}")
        return pl.DataFrame()

    rows = []
    for m in all_markets:
        q = m.get("question", "").lower()
        if not any(k in q for k in _POLY_GEO_KEYWORDS):
            continue
        if any(k in q for k in _POLY_EXCLUDE):
            continue

        raw_prices = m.get("outcomePrices", "[]")
        try:
            import json as _json
            prices = _json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices
            yes_prob = float(prices[0]) if prices else 0.5
            no_prob  = float(prices[1]) if len(prices) > 1 else 1 - yes_prob
        except Exception:
            yes_prob, no_prob = 0.5, 0.5

        slug     = m.get("slug", "")
        end_date = (m.get("endDate") or "")[:10]
        liq      = float(m.get("liquidity", 0))

        # Tag category by question content
        ql = m.get("question", "").lower()
        if "taiwan" in ql or "china" in ql:
            cat = "China / Taiwan"
        elif "iran" in ql:
            cat = "Iran"
        elif "ukraine" in ql or "russia" in ql or "ceasefire" in ql:
            cat = "Russia / Ukraine"
        elif "recession" in ql or "fed" in ql:
            cat = "US Macro"
        else:
            cat = "Geopolitical"

        rows.append({
            "question":  m.get("question", ""),
            "yes_prob":  round(yes_prob, 4),
            "no_prob":   round(no_prob, 4),
            "liquidity": round(liq, 0),
            "end_date":  end_date,
            "url":       f"https://polymarket.com/event/{slug}",
            "category":  cat,
        })

    if not rows:
        return pl.DataFrame()

    return (
        pl.DataFrame(rows)
        .sort("liquidity", descending=True)
        .head(max_markets)
    )


# ── Finnhub News ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=900)
def fetch_finnhub_news(tickers: list[str] | None = None, limit: int = 50) -> pl.DataFrame:
    """
    Fetch company news from Finnhub API for given tickers.
    Covers Reuters, AP, MarketWatch, Bloomberg wire, CNBC, and more.
    Cached for 15 minutes.

    Args:
        tickers: List of ticker symbols. Falls back to all VARTA tickers.
        limit: Max articles per ticker before dedup (default 50).
    Returns:
        DataFrame with columns: headline, summary, url, source, published_at, tickers
    Example:
        df = fetch_finnhub_news(tickers=["NVDA", "TSM"])
    """
    if not FINNHUB_API_KEY:
        log.warning("Finnhub API key missing — skipping Finnhub news fetch")
        return pl.DataFrame()

    from datetime import date, timedelta
    symbols = tickers or TICKERS
    date_to   = date.today().strftime("%Y-%m-%d")
    date_from = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")

    rows = []
    seen_headlines: set[str] = set()

    for symbol in symbols[:8]:   # cap at 8 tickers to stay within free-tier rate limits
        url = "https://finnhub.io/api/v1/company-news"
        params = {
            "symbol": symbol,
            "from":   date_from,
            "to":     date_to,
            "token":  FINNHUB_API_KEY,
        }
        try:
            resp = requests.get(url, params=params, timeout=8)
            resp.raise_for_status()
            articles = resp.json()
            if not isinstance(articles, list):
                continue
            for a in articles[:limit]:
                headline = a.get("headline", "").strip()
                if not headline or headline in seen_headlines:
                    continue
                seen_headlines.add(headline)
                import datetime as _dt
                ts = a.get("datetime", 0)
                published = _dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else ""
                rows.append({
                    "headline":     headline,
                    "summary":      a.get("summary", ""),
                    "url":          a.get("url", ""),
                    "source":       a.get("source", "finnhub"),
                    "published_at": published,
                    "tickers":      symbol,
                })
        except Exception as e:
            log.warning(f"Finnhub news fetch failed for {symbol}: {e}")
            continue

    if not rows:
        return pl.DataFrame()

    return pl.DataFrame(rows).with_columns(
        pl.col("published_at").str.to_datetime(
            format="%Y-%m-%dT%H:%M:%SZ", strict=False,
            time_unit="us", time_zone="UTC",
        )
    )


# ── Alpaca Trade Execution ────────────────────────────────────────────────────

def submit_market_order(
    ticker: str,
    qty: float,
    side: str,          # "buy" or "sell"
) -> dict:
    """
    Submit a market order to Alpaca paper account.
    Always paper=True — never touches real money.

    Args:
        ticker: Ticker symbol (e.g. "GLD").
        qty: Number of shares.
        side: "buy" or "sell".
    Returns:
        Dict with order_id, status, symbol, qty, side or error key.
    Example:
        result = submit_market_order("GLD", 10, "buy")
    """
    try:
        client = get_trading_client()
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        req = MarketOrderRequest(
            symbol=ticker,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        order = client.submit_order(req)
        log.info(f"Paper order submitted: {side.upper()} {qty} {ticker} → {order.status}")
        return {
            "order_id": str(order.id),
            "status":   str(order.status.value),
            "symbol":   order.symbol,
            "qty":      float(order.qty),
            "side":     str(order.side.value),
        }
    except Exception as e:
        log.error(f"Order failed {side} {qty} {ticker}: {e}")
        return {"error": str(e), "symbol": ticker, "side": side, "qty": qty}


@st.cache_data(ttl=30)
def fetch_recent_orders(limit: int = 20) -> pl.DataFrame:
    """
    Fetch recent orders from Alpaca paper account.

    Args:
        limit: Number of recent orders to return.
    Returns:
        DataFrame with columns: submitted_at, symbol, side, qty, status, filled_avg_price
    Example:
        df = fetch_recent_orders()
    """
    try:
        client = get_trading_client()
        req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=limit)
        orders = client.get_orders(req)
        if not orders:
            return pl.DataFrame()
        rows = []
        for o in orders:
            rows.append({
                "submitted_at":    str(o.submitted_at)[:19] if o.submitted_at else "",
                "symbol":          o.symbol,
                "side":            str(o.side.value),
                "qty":             float(o.qty) if o.qty else 0.0,
                "status":          str(o.status.value),
                "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price else 0.0,
            })
        return pl.DataFrame(rows)
    except Exception as e:
        log.error(f"Fetch orders failed: {e}")
        return pl.DataFrame()
