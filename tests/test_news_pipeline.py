"""refresh_news end to end with fixture sources and scorers."""

from datetime import UTC, datetime

import pytest

from api.db import connect, init_db
from api.news_fixtures import fixture_sources
from api.news_pipeline import MARKET, Sources, refresh_news, tracked_securities
from api.scoring import HeuristicScorer

NOW = datetime(2026, 10, 12, 15, 0, tzinfo=UTC)


class NoneScorer:
    def score(self, *a):
        return None


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "v.db")
    init_db(c)
    return c


def _count(c, sql):
    return c.execute(sql).fetchone()[0]


def test_refresh_stores_dedupes_scores(conn):
    out = refresh_news(conn, fixture_sources(NOW), HeuristicScorer(), NOW)
    assert out["duplicates"] >= 1
    assert out["stored"] == _count(conn, "SELECT COUNT(*) FROM news_items")
    assert out["scored"] == _count(conn, "SELECT COUNT(*) FROM news_scores")
    assert out["unscored"] == 0 and out["markets"] == 3
    assert _count(conn, f"SELECT COUNT(*) FROM news_scores WHERE ticker='{MARKET}'") >= 2
    heuristic = _count(conn, "SELECT COUNT(*) FROM news_scores WHERE scored_by='heuristic-v1'")
    assert heuristic == out["scored"]


def test_second_refresh_is_noop(conn):
    refresh_news(conn, fixture_sources(NOW), HeuristicScorer(), NOW)
    out = refresh_news(conn, fixture_sources(NOW), HeuristicScorer(), NOW)
    assert out["stored"] == 0 and out["scored"] == 0


def test_retention_drops_old(conn):
    out = refresh_news(conn, fixture_sources(NOW), HeuristicScorer(), NOW)
    assert out["deleted"] >= 1
    oldest = conn.execute("SELECT MIN(published_at) FROM news_items").fetchone()[0]
    assert oldest >= "2026-07-14"


def test_failing_source_does_not_stop_others(conn):
    good = fixture_sources(NOW)

    def broken(tickers):
        raise RuntimeError("boom")

    srcs = Sources(news=[("broken", broken), *good.news], markets=good.markets)
    out = refresh_news(conn, srcs, HeuristicScorer(), NOW)
    assert out["fetched"]["broken"] == 0 and out["stored"] > 0


def test_scorer_down_uses_fallback_then_leaves_unscored(conn):
    out = refresh_news(conn, fixture_sources(NOW), NoneScorer(), NOW, fallback=HeuristicScorer())
    assert out["unscored"] == 0 and out["scored"] > 0
    out2 = refresh_news(conn, fixture_sources(NOW), NoneScorer(), NOW)
    assert out2["scored"] == 0


def test_unscored_pairs_retried_next_run(conn):
    first = refresh_news(conn, fixture_sources(NOW), NoneScorer(), NOW)
    assert first["unscored"] > 0
    second = refresh_news(conn, Sources(news=[]), HeuristicScorer(), NOW)
    assert second["scored"] == first["unscored"]


def test_tracked_securities_falls_back_to_watchlist(conn):
    assert "SPY" in tracked_securities(conn)
