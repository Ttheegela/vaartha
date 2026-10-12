"""News refresh: fetch, dedupe, tag, score, store prediction markets, apply retention."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from api.news_sources import (
    Market,
    fetch_alpaca,
    fetch_edgar,
    fetch_finnhub,
    fetch_gdelt,
    fetch_polymarket,
    fetch_rss,
)
from api.scoring import Scorer
from api.settings import Settings
from core.news import RawItem, tag_tickers, tag_topics, title_hash, url_hash

log = logging.getLogger(__name__)

MARKET = "MARKET"
MAX_SCORES_PER_RUN = 200
RETENTION_DAYS = 90
NEWS_CHANNEL = "news"
DEFAULT_WATCHLIST: dict[str, tuple[str, ...]] = {
    "SPY": ("s&p 500",), "NVDA": ("nvidia",), "TSM": ("tsmc", "taiwan semiconductor"),
    "XOM": ("exxon",), "GLD": ("gold",),
}
NAME_SUFFIXES = (" corp", " inc", " ltd", " plc", " co", " corporation", " incorporated",
                 " etf", " shares")


@dataclass
class Sources:
    """Injectable fetchers so tests and demo mode never touch the network."""

    news: list[tuple[str, Callable[[list[str]], list[RawItem]]]]
    markets: Callable[[], list[Market]] | None = None


def tracked_securities(conn) -> dict[str, tuple[str, ...]]:
    """Held tickers mapped to name aliases; the default watchlist when nothing is held."""
    rows = conn.execute(
        "SELECT DISTINCT s.ticker, s.name FROM holdings h "
        "JOIN securities s ON s.security_id = h.security_id WHERE s.ticker IS NOT NULL"
    ).fetchall()
    out: dict[str, tuple[str, ...]] = {}
    for ticker, name in rows:
        aliases = []
        if name:
            full = name.lower().strip()
            short = full
            for suffix in NAME_SUFFIXES:
                if short.endswith(suffix):
                    short = short[: -len(suffix)].strip()
            aliases = list(dict.fromkeys([full, short]))
        out[ticker] = tuple(aliases)
    return out or dict(DEFAULT_WATCHLIST)


def default_sources(settings: Settings, today: date) -> Sources:
    """Live sources wired from settings."""
    s = settings
    return Sources(
        news=[
            ("Alpaca", lambda t: fetch_alpaca(s.alpaca_key, s.alpaca_secret, t)),
            ("Finnhub", lambda t: fetch_finnhub(s.finnhub_key, t, today)),
            ("RSS", lambda t: fetch_rss()),
            ("GDELT", lambda t: fetch_gdelt()),
            ("EDGAR", lambda t: fetch_edgar(s.sec_user_agent, t, today)),
        ],
        markets=fetch_polymarket,
    )


def _fetch_all(sources: Sources, tickers: list[str]) -> tuple[dict[str, int], list[RawItem]]:
    """Run every source; a failing source counts 0 and never stops the others."""
    counts, items = {}, []
    for name, fetch in sources.news:
        try:
            got = fetch(tickers)
        except Exception as exc:
            log.warning("news source %s failed: %s", name, type(exc).__name__)
            got = []
        counts[name] = len(got)
        items.extend(got)
    return counts, items


def _store(conn, items: list[RawItem], securities, cutoff: str) -> tuple[int, int]:
    """Insert unseen items; returns (stored fresh, duplicates)."""
    stored = dups = 0
    for it in items:
        uh, th = url_hash(it.url), title_hash(it.title)
        if conn.execute("SELECT 1 FROM news_items WHERE url_hash=? OR title_hash=?",
                        (uh, th)).fetchone():
            dups += 1
            continue
        tickers = tag_tickers(it, securities) or [MARKET]
        topics = tag_topics(f"{it.title} {it.text}")
        conn.execute(
            "INSERT INTO news_items (published_at, source, url, title, text, tickers, topics, "
            "url_hash, title_hash) VALUES (?,?,?,?,?,?,?,?,?)",
            (it.published_at, it.source, it.url, it.title, it.text, json.dumps(tickers),
             json.dumps(topics), uh, th))
        stored += it.published_at >= cutoff
    return stored, dups


def _score_pending(conn, scorer: Scorer, fallback: Scorer | None, securities, now: datetime,
                   cutoff: str) -> tuple[int, int]:
    """Score unscored (news, ticker) pairs, newest first; returns (scored, unscored)."""
    pairs = conn.execute(
        "SELECT n.id, j.value, n.title, n.text, n.source FROM news_items n, json_each(n.tickers) j "
        "LEFT JOIN news_scores s ON s.news_id = n.id AND s.ticker = j.value "
        "WHERE s.news_id IS NULL AND n.published_at >= ? ORDER BY n.published_at DESC LIMIT ?",
        (cutoff, MAX_SCORES_PER_RUN)).fetchall()
    scored = unscored = 0
    for news_id, ticker, title, text, source in pairs:
        company = securities[ticker][0] if securities.get(ticker) else ""
        args = (title, text or "", source, ticker, company)
        result = scorer.score(*args) or (fallback.score(*args) if fallback else None)
        if result is None:
            unscored += 1
            continue
        conn.execute(
            "INSERT INTO news_scores (news_id, ticker, sentiment, sentiment_conf, material, "
            "stress, event, noise, raw_json, scored_at, channel, scored_by) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (news_id, ticker, result.sentiment, result.sentiment_conf, result.material,
             result.stress, result.event, result.noise, json.dumps(result.raw),
             now.isoformat(), NEWS_CHANNEL, result.scored_by))
        scored += 1
    return scored, unscored


def refresh_news(conn, sources: Sources, scorer: Scorer, now: datetime,
                 fallback: Scorer | None = None) -> dict:
    """One full refresh cycle; returns counters for each stage."""
    securities = tracked_securities(conn)
    cutoff = (now - timedelta(days=RETENTION_DAYS)).isoformat()
    fetched, items = _fetch_all(sources, list(securities))
    stored, dups = _store(conn, items, securities, cutoff)
    scored, unscored = _score_pending(conn, scorer, fallback, securities, now, cutoff)

    markets = []
    if sources.markets:
        try:
            markets = sources.markets()
        except Exception as exc:
            log.warning("markets source failed: %s", type(exc).__name__)
    for m in markets:
        conn.execute(
            "INSERT OR REPLACE INTO crowd_odds (market_id, question, yes_prob, liquidity, "
            "end_date, url, category, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
            (m.market_id, m.question, m.yes_prob, m.liquidity, m.end_date, m.url, m.category,
             now.isoformat()))

    deleted = conn.execute("DELETE FROM news_items WHERE published_at < ?", (cutoff,)).rowcount
    conn.commit()
    return {"fetched": fetched, "stored": stored, "duplicates": dups, "scored": scored,
            "unscored": unscored, "markets": len(markets), "deleted": deleted}
