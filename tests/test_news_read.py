"""Read endpoints for news, sentiment, crowd odds and holdings."""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from api.crypto import TokenBox, new_key
from api.db import connect, init_db
from api.main import create_app
from api.news_fixtures import fixture_sources
from api.news_pipeline import refresh_news
from api.plaid_fake import FakePlaid
from api.scoring import HeuristicScorer
from api.settings import Settings
from api.sync import link_item
from core.regime import compute_regime

NOW = datetime(2026, 10, 12, 15, 0, tzinfo=UTC)
TODAY = NOW.date()
NORMAL = compute_regime([100.0] * 40, [100.0] * 40, [1800.0] * 40)


def _client(path):
    app = create_app(Settings(db_path=path, instance="demo"), regime_provider=lambda: NORMAL,
                     today=lambda: TODAY)
    return TestClient(app)


@pytest.fixture
def seeded(tmp_path):
    path = tmp_path / "v.db"
    conn = connect(path)
    init_db(conn)
    link_item(conn, FakePlaid(date(2026, 10, 12)), TokenBox(new_key()), "public-fake-1", TODAY)
    refresh_news(conn, fixture_sources(NOW), HeuristicScorer(), NOW)
    conn.close()
    return _client(path)


@pytest.fixture
def empty(tmp_path):
    return _client(tmp_path / "v.db")


def test_news_default_filters(seeded):
    items = seeded.get("/api/news").json()
    assert len(items) >= 1
    for it in items:
        assert any(s["noise"] <= 0.7 and s["material"] >= 0.3 for s in it["scores"])
    dates = [i["published_at"] for i in items]
    assert dates == sorted(dates, reverse=True)


def test_news_all_includes_at_least_material(seeded):
    all_items = seeded.get("/api/news?material_only=false&days=30").json()
    assert len(all_items) >= len(seeded.get("/api/news").json())


def test_news_ticker_filter(seeded):
    items = seeded.get("/api/news?ticker=NVDA&material_only=false&days=30").json()
    assert items and all("NVDA" in i["tickers"] for i in items)


def test_news_source_filter(seeded):
    src = seeded.get("/api/news?material_only=false&days=30").json()[0]["source"]
    items = seeded.get("/api/news", params={"source": src, "material_only": "false",
                                            "days": 30}).json()
    assert items and {i["source"] for i in items} == {src}


def test_news_days_bounds(seeded):
    assert seeded.get("/api/news?days=0").status_code == 422


def test_sentiment_nvda(seeded):
    pts = seeded.get("/api/sentiment?ticker=NVDA&days=30").json()
    assert pts
    for p in pts:
        assert p["channel"] in ("news", "crowd") and -1 <= p["sentiment"] <= 1 and p["items"] >= 1
    assert any(p["channel"] == "news" for p in pts)


def test_sentiment_requires_ticker(seeded):
    assert seeded.get("/api/sentiment").status_code == 422
    assert seeded.get("/api/sentiment?ticker=NVDA&days=0").status_code == 422


def test_crowd_odds_sorted(seeded):
    rows = seeded.get("/api/crowd_odds").json()
    assert rows
    liq = [r["liquidity"] or 0 for r in rows]
    assert liq == sorted(liq, reverse=True)


def test_holdings_weights_sum_to_one(seeded):
    rows = seeded.get("/api/holdings").json()
    assert rows
    assert sum(r["weight"] for r in rows) == pytest.approx(1.0, abs=1e-6)


def test_empty_db_returns_empty_lists(empty):
    for url in ("/api/news", "/api/sentiment?ticker=NVDA", "/api/crowd_odds", "/api/holdings"):
        assert empty.get(url).json() == []
