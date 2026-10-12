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


def test_holdings_aggregate_same_security_across_accounts(tmp_path):
    path = tmp_path / "v.db"
    conn = connect(path)
    init_db(conn)
    link_item(conn, FakePlaid(date(2026, 10, 12)), TokenBox(new_key()), "public-fake-1", TODAY)
    before = {r["ticker"]: r for r in _client(path).get("/api/holdings").json()}
    h = conn.execute("SELECT * FROM holdings ORDER BY value DESC LIMIT 1").fetchone()
    other = conn.execute("SELECT account_id FROM accounts WHERE account_id != ?",
                         (h["account_id"],)).fetchone()["account_id"]
    conn.execute("INSERT INTO holdings (account_id, security_id, quantity, cost_basis, value, "
                 "as_of) "
                 "VALUES (?,?,?,?,?,?)",
                 (other, h["security_id"], h["quantity"], h["cost_basis"], h["value"], h["as_of"]))
    conn.commit()
    conn.close()
    rows = _client(path).get("/api/holdings").json()
    tickers = [r["ticker"] for r in rows if r["ticker"]]
    assert len(tickers) == len(set(tickers))
    dup = next(r for r in rows if r["value"] == pytest.approx(2 * h["value"]))
    assert dup["quantity"] == pytest.approx(2 * h["quantity"])
    assert len(rows) == len(before)
    assert [r["value"] for r in rows] == sorted((r["value"] for r in rows), reverse=True)
    assert sum(r["weight"] for r in rows) == pytest.approx(1.0, abs=1e-6)


def test_empty_db_returns_empty_lists(empty):
    for url in ("/api/news", "/api/sentiment?ticker=NVDA", "/api/crowd_odds", "/api/holdings"):
        assert empty.get(url).json() == []


def test_holdings_weights_sum_to_one_with_tickerless_holding(tmp_path):
    path = tmp_path / "v.db"
    conn = connect(path)
    init_db(conn)
    link_item(conn, FakePlaid(date(2026, 10, 12)), TokenBox(new_key()), "public-fake-1", TODAY)
    h = conn.execute("SELECT * FROM holdings LIMIT 1").fetchone()
    conn.execute("INSERT INTO securities (security_id, ticker, name) "
                 "VALUES ('cash1', NULL, 'Cash')")
    conn.execute("INSERT INTO holdings (account_id, security_id, quantity, value, as_of) "
                 "VALUES (?, 'cash1', 1, 500, ?)", (h["account_id"], h["as_of"]))
    conn.commit()
    conn.close()
    rows = _client(path).get("/api/holdings").json()
    assert any(r["ticker"] is None and r["weight"] > 0 for r in rows)
    assert sum(r["weight"] for r in rows) == pytest.approx(1.0, abs=1e-6)
