"""News sources. Every fetcher is fail-soft: it returns [] and logs the source and error type."""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx

from core.news import RawItem

log = logging.getLogger(__name__)

ALPACA_NEWS_URL = "https://data.alpaca.markets/v1beta1/news"
FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/company-news"
RSS_FEEDS = (("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
             ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"))
TIMEOUT_SECONDS = 10.0
FINNHUB_MAX_SYMBOLS = 8
_TAG = re.compile(r"<[^>]+>")


def _client(transport: httpx.BaseTransport | None) -> httpx.Client:
    """HTTP client with the shared timeout."""
    return httpx.Client(timeout=TIMEOUT_SECONDS, transport=transport)


def _iso(dt: datetime) -> str:
    """UTC timestamp as YYYY-MM-DDTHH:MM:SSZ (naive input is treated as UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_alpaca(key: str | None, secret: str | None, symbols: list[str], *, limit: int = 50,
                 transport: httpx.BaseTransport | None = None) -> list[RawItem]:
    """Latest Alpaca news for the symbols; [] without credentials or on any failure."""
    if not key or not secret:
        return []
    try:
        with _client(transport) as c:
            r = c.get(
                ALPACA_NEWS_URL,
                headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
                params={"symbols": ",".join(symbols), "limit": limit, "sort": "desc"},
            )
            r.raise_for_status()
            rows = r.json()["news"]
        items = []
        for n in rows:
            try:
                if not n.get("headline"):
                    continue
                items.append(RawItem(
                    f"Alpaca/{n['source']}", n["url"], n["headline"], n.get("summary") or "",
                    _iso(datetime.fromisoformat(n["created_at"].replace("Z", "+00:00"))),
                    tuple(n.get("symbols") or ()),
                ))
            except Exception as exc:
                log.warning("alpaca item skipped: %s", type(exc).__name__)
        return items
    except Exception as exc:
        log.warning("alpaca fetch failed: %s", type(exc).__name__)
        return []


def fetch_finnhub(key: str | None, symbols: list[str], today: date, *, days: int = 3,
                  transport: httpx.BaseTransport | None = None) -> list[RawItem]:
    """Finnhub company news per symbol (first FINNHUB_MAX_SYMBOLS); a failing symbol is skipped."""
    if not key:
        return []
    items: list[RawItem] = []
    try:
        with _client(transport) as c:
            for sym in symbols[:FINNHUB_MAX_SYMBOLS]:
                try:
                    r = c.get(
                        FINNHUB_NEWS_URL,
                        headers={"X-Finnhub-Token": key},
                        params={"symbol": sym, "from": (today - timedelta(days=days)).isoformat(),
                                "to": today.isoformat()},
                    )
                    r.raise_for_status()
                    articles = r.json()
                    for n in articles:
                        try:
                            if not n.get("headline"):
                                continue
                            items.append(RawItem(
                                f"Finnhub/{n['source']}", n["url"], n["headline"],
                                n.get("summary") or "",
                                _iso(datetime.fromtimestamp(n["datetime"], tz=UTC)), (sym,),
                            ))
                        except Exception as exc:
                            log.warning("finnhub item skipped: %s", type(exc).__name__)
                except Exception as exc:
                    log.warning("finnhub fetch failed: %s", type(exc).__name__)
    except Exception as exc:
        log.warning("finnhub fetch failed: %s", type(exc).__name__)
    return items


def fetch_rss(feeds=RSS_FEEDS, *, transport: httpx.BaseTransport | None = None) -> list[RawItem]:
    """RSS items from each (label, url) feed; a failing feed is skipped."""
    items: list[RawItem] = []
    try:
        with _client(transport) as c:
            for label, url in feeds:
                try:
                    r = c.get(url)
                    r.raise_for_status()
                    for it in ET.fromstring(r.text).iter("item"):
                        try:
                            title = (it.findtext("title") or "").strip()
                            link = (it.findtext("link") or "").strip()
                            if not title or not link:
                                continue
                            text = _TAG.sub("", it.findtext("description") or "").strip()
                            when = _iso(parsedate_to_datetime(it.findtext("pubDate") or ""))
                            items.append(RawItem(label, link, title, text, when))
                        except Exception as exc:
                            log.warning("rss item skipped: %s", type(exc).__name__)
                except Exception as exc:
                    log.warning("rss fetch failed: %s", type(exc).__name__)
    except Exception as exc:
        log.warning("rss fetch failed: %s", type(exc).__name__)
    return items
