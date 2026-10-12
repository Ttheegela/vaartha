"""News sources. Every fetcher is fail-soft: it returns [] and logs the source and error type."""

import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
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
MAX_RESPONSE_BYTES = 5_000_000
FINNHUB_MAX_SYMBOLS = 8
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERY = (
    '(sanctions OR tariffs OR "export controls" OR OPEC OR "Strait of Hormuz" OR ceasefire) '
    "sourcelang:english"
)
GDELT_MAX_RECORDS = 75
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_DAYS = 7
POLYMARKET_URL = "https://gamma-api.polymarket.com/markets"
POLY_INCLUDE = (
    "taiwan", "iran", "ukraine", "ceasefire", "russia invade",
    "china blockade", "us invade", "nuclear deal", "us recession",
    "china invad", "nato", "iranian regime",
)
POLY_EXCLUDE = (
    "fifa", "world cup", "nhl", "nba", "nfl", "mlb", "super bowl",
    "oscar", "grammy", "bitcoin", "crypto", "election", "senator",
    "governor", "nominee", "primary",
)
POLY_PAGES = (0, 500, 1000)
POLY_MAX_MARKETS = 10
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Market:
    """A prediction market relevant to the tracked geopolitical themes."""

    market_id: str
    question: str
    yes_prob: float
    liquidity: float
    end_date: str
    url: str
    category: str


def _client(transport: httpx.BaseTransport | None) -> httpx.Client:
    """HTTP client with the shared timeout."""
    return httpx.Client(timeout=TIMEOUT_SECONDS, transport=transport)


def _iso(dt: datetime) -> str:
    """UTC timestamp as YYYY-MM-DDTHH:MM:SSZ (naive input is treated as UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check(r: httpx.Response, source: str) -> None:
    """Raise on an HTTP error status or a body over MAX_RESPONSE_BYTES (logged by source)."""
    r.raise_for_status()
    if len(r.content) > MAX_RESPONSE_BYTES:
        log.warning("%s response too large", source)
        raise ValueError("response too large")


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
            _check(r, "alpaca")
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
                    _check(r, "finnhub")
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
                    _check(r, "rss")
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


def fetch_gdelt(*, transport: httpx.BaseTransport | None = None) -> list[RawItem]:
    """Recent GDELT articles for the geopolitical query; [] on rate-limit text or any failure."""
    try:
        with _client(transport) as c:
            r = c.get(GDELT_URL, params={
                "query": GDELT_QUERY, "mode": "artlist", "format": "json",
                "maxrecords": GDELT_MAX_RECORDS, "timespan": "1d", "sort": "datedesc"})
            _check(r, "gdelt")
            try:
                articles = r.json()["articles"]
            except (ValueError, KeyError):  # rate-limit text is not JSON
                return []
        items = []
        for a in articles:
            try:
                if not a.get("url") or not a.get("title"):
                    continue
                when = _iso(datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ"))
                source = f"GDELT/{a.get('domain') or 'unknown'}"
                items.append(RawItem(source, a["url"], a["title"], "", when))
            except Exception as exc:
                log.warning("gdelt item skipped: %s", type(exc).__name__)
        return items
    except Exception as exc:
        log.warning("gdelt fetch failed: %s", type(exc).__name__)
        return []


def fetch_edgar(user_agent: str | None, tickers: list[str], today: date, *,
                transport: httpx.BaseTransport | None = None) -> list[RawItem]:
    """Recent 8-K filings for tracked tickers; [] without a User-Agent; bad tickers skipped."""
    if not user_agent:
        return []
    items: list[RawItem] = []
    cutoff = (today - timedelta(days=EDGAR_DAYS)).isoformat()
    try:
        with _client(transport) as c:
            headers = {"User-Agent": user_agent}
            r = c.get(SEC_TICKERS_URL, headers=headers)
            _check(r, "edgar")
            ciks = {}
            for v in r.json().values():
                try:
                    ciks[v["ticker"]] = (int(v["cik_str"]), v["title"])
                except Exception as exc:
                    log.warning("edgar ticker entry skipped: %s", type(exc).__name__)
            for sym in tickers:
                if sym not in ciks:
                    continue
                try:
                    cik, company = ciks[sym]
                    r = c.get(SEC_SUBMISSIONS_URL.format(cik=f"{cik:010d}"), headers=headers)
                    _check(r, "edgar")
                    recent = r.json()["filings"]["recent"]
                    for form, filed, acc, doc in zip(recent["form"], recent["filingDate"],
                                                     recent["accessionNumber"],
                                                     recent["primaryDocument"], strict=False):
                        try:
                            if form != "8-K" or not cutoff <= filed <= today.isoformat():
                                continue
                            url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                                   f"{acc.replace('-', '')}/{doc}")
                            items.append(RawItem(
                                "SEC EDGAR", url,
                                f"{company} files 8-K ({filed})", "", f"{filed}T00:00:00Z", (sym,)))
                        except Exception as exc:
                            log.warning("edgar item skipped: %s", type(exc).__name__)
                except Exception as exc:
                    log.warning("edgar fetch failed: %s", type(exc).__name__)
    except Exception as exc:
        log.warning("edgar fetch failed: %s", type(exc).__name__)
    return items


def _poly_category(q: str) -> str:
    """Theme label for a lowercased market question."""
    if "taiwan" in q or "china" in q:
        return "China / Taiwan"
    if "iran" in q:
        return "Iran"
    if "ukraine" in q or "russia" in q or "ceasefire" in q:
        return "Russia / Ukraine"
    if "recession" in q or "fed" in q:
        return "US Macro"
    return "Geopolitical"


def fetch_polymarket(*, transport: httpx.BaseTransport | None = None) -> list[Market]:
    """Top POLY_MAX_MARKETS relevant active markets by liquidity; [] on failure."""
    try:
        raw: list[dict] = []
        with _client(transport) as c:
            for offset in POLY_PAGES:
                r = c.get(POLYMARKET_URL, params={"active": "true", "limit": 500, "offset": offset})
                _check(r, "polymarket")
                batch = r.json()
                if not batch:
                    break
                raw.extend(batch)
        markets = []
        for m in raw:
            try:
                q = m["question"].lower()
                if not any(k in q for k in POLY_INCLUDE) or any(k in q for k in POLY_EXCLUDE):
                    continue
                prices = m["outcomePrices"]
                prices = json.loads(prices) if isinstance(prices, str) else prices
                markets.append(Market(
                    str(m.get("id") or m["slug"]), m["question"], round(float(prices[0]), 4),
                    float(m.get("liquidity") or 0), (m.get("endDate") or "")[:10],
                    f"https://polymarket.com/event/{m.get('slug', '')}", _poly_category(q)))
            except Exception as exc:
                log.warning("polymarket item skipped: %s", type(exc).__name__)
        return sorted(markets, key=lambda x: x.liquidity, reverse=True)[:POLY_MAX_MARKETS]
    except Exception as exc:
        log.warning("polymarket fetch failed: %s", type(exc).__name__)
        return []
