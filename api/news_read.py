"""Read-only news, sentiment, crowd-odds and holdings endpoints over SQLite."""

import json
from collections.abc import Callable
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api.db import connect

NOISE_MAX = 0.7
MATERIAL_MIN = 0.3
DEFAULT_NEWS_DAYS = 7
MAX_NEWS_ITEMS = 100
DEFAULT_SENTIMENT_DAYS = 30
MAX_SENTIMENT_DAYS = 365
STRESS_LABELS = ("none", "localized", "sector", "systemic")


class TickerScore(BaseModel):
    """One ticker's score for a news item."""

    ticker: str
    sentiment: float
    sentiment_conf: float
    material: float
    stress: Literal["none", "localized", "sector", "systemic"]
    event: str
    noise: float
    scored_by: str


class NewsItemOut(BaseModel):
    """A stored news item with its per-ticker scores."""

    id: int
    published_at: str
    source: str
    url: str | None
    title: str
    tickers: list[str]
    topics: list[str]
    scores: list[TickerScore]


class SentimentPoint(BaseModel):
    """Confidence-weighted mean sentiment for one day and channel."""

    date: str
    channel: Literal["news", "crowd"]
    sentiment: float
    items: int


class CrowdOddsOut(BaseModel):
    """A prediction-market question with its yes probability."""

    market_id: str
    question: str
    yes_prob: float
    liquidity: float | None
    end_date: str | None
    url: str | None
    category: str | None


class HoldingOut(BaseModel):
    """A held security with its share of total portfolio value."""

    ticker: str | None
    name: str | None
    quantity: float | None
    value: float | None
    cost_basis: float | None
    weight: float


def _stress_label(raw: float | None) -> str:
    """Map a raw 0..3 stress score to its label, clamped."""
    return STRESS_LABELS[min(3, max(0, round(raw or 0)))]


def build_news_router(db_path: Path, today: Callable[[], date]) -> APIRouter:
    """Routes for news, sentiment, crowd odds and holdings."""
    router = APIRouter(prefix="/api")

    @router.get("/news", response_model=list[NewsItemOut])
    def news(ticker: str | None = None, source: str | None = None,
             days: int = Query(DEFAULT_NEWS_DAYS, ge=1, le=MAX_SENTIMENT_DAYS),
             material_only: bool = True) -> list[NewsItemOut]:
        """Newest-first news; by default only items with a material, non-noise score."""
        where, args = ["n.published_at >= ?"], [(today() - timedelta(days=days)).isoformat()]
        if ticker:
            where.append("EXISTS (SELECT 1 FROM json_each(n.tickers) WHERE value = ?)")
            args.append(ticker)
        if source:
            where.append("n.source = ?")
            args.append(source)
        if material_only:
            where.append("EXISTS (SELECT 1 FROM news_scores s WHERE s.news_id = n.id "
                         "AND s.noise <= ? AND s.material >= ?)")
            args += [NOISE_MAX, MATERIAL_MIN]
        with closing(connect(db_path)) as conn:
            rows = conn.execute(
                f"SELECT n.id, n.published_at, n.source, n.url, n.title, n.tickers, n.topics "
                f"FROM news_items n WHERE {' AND '.join(where)} "
                "ORDER BY n.published_at DESC, n.id DESC LIMIT ?",
                (*args, MAX_NEWS_ITEMS)).fetchall()
            scores: dict[int, list[TickerScore]] = {}
            for s in conn.execute(
                    "SELECT news_id, ticker, sentiment, sentiment_conf, material, stress, event, "
                    "noise, scored_by FROM news_scores "
                    f"WHERE news_id IN ({','.join('?' * len(rows))}) ORDER BY ticker",
                    [r["id"] for r in rows]):
                scores.setdefault(s["news_id"], []).append(TickerScore(
                    ticker=s["ticker"], sentiment=s["sentiment"] or 0,
                    sentiment_conf=s["sentiment_conf"] or 0, material=s["material"] or 0,
                    stress=_stress_label(s["stress"]), event=s["event"] or "",
                    noise=s["noise"] or 0, scored_by=s["scored_by"] or ""))
        return [NewsItemOut(id=r["id"], published_at=r["published_at"], source=r["source"],
                            url=r["url"], title=r["title"], tickers=json.loads(r["tickers"]),
                            topics=json.loads(r["topics"]), scores=scores.get(r["id"], []))
                for r in rows]

    @router.get("/sentiment", response_model=list[SentimentPoint])
    def sentiment(ticker: str, days: int = Query(
            DEFAULT_SENTIMENT_DAYS, ge=1, le=MAX_SENTIMENT_DAYS)) -> list[SentimentPoint]:
        """Daily confidence-weighted mean sentiment per channel for one ticker, oldest first."""
        cutoff = (today() - timedelta(days=days)).isoformat()
        with closing(connect(db_path)) as conn:
            rows = conn.execute(
                "SELECT substr(n.published_at, 1, 10) AS day, s.channel, "
                "SUM(s.sentiment * s.sentiment_conf) / SUM(s.sentiment_conf) AS mean, "
                "COUNT(*) AS items FROM news_scores s JOIN news_items n ON n.id = s.news_id "
                "WHERE s.ticker = ? AND n.published_at >= ? AND s.sentiment IS NOT NULL "
                "GROUP BY day, s.channel HAVING SUM(s.sentiment_conf) > 0 "
                "ORDER BY day, s.channel", (ticker, cutoff)).fetchall()
        return [SentimentPoint(date=r["day"], channel=r["channel"], sentiment=r["mean"],
                               items=r["items"]) for r in rows]

    @router.get("/crowd_odds", response_model=list[CrowdOddsOut])
    def crowd_odds() -> list[CrowdOddsOut]:
        """Prediction-market odds, most liquid first."""
        with closing(connect(db_path)) as conn:
            rows = conn.execute(
                "SELECT market_id, question, yes_prob, liquidity, end_date, url, category "
                "FROM crowd_odds ORDER BY liquidity DESC, market_id").fetchall()
        return [CrowdOddsOut(**dict(r)) for r in rows]

    @router.get("/holdings", response_model=list[HoldingOut])
    def holdings() -> list[HoldingOut]:
        """Holdings by value descending, with weight = value / total value."""
        with closing(connect(db_path)) as conn:
            rows = conn.execute(
                "SELECT s.ticker, s.name, h.quantity, h.value, h.cost_basis FROM holdings h "
                "JOIN securities s USING (security_id) ORDER BY h.value DESC").fetchall()
        total = sum(r["value"] or 0 for r in rows)
        return [HoldingOut(**dict(r), weight=(r["value"] or 0) / total if total else 0.0)
                for r in rows]

    return router
