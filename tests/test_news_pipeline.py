"""refresh_news end to end with fixture sources and scorers."""

import json
from datetime import UTC, datetime

import pytest

from api.db import connect, init_db
from api.news_fixtures import fixture_sources
from api.news_pipeline import MARKET, Sources, refresh_news, tracked_securities
from api.scoring import HeuristicScorer
from core.news import RawItem, tag_tickers

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


def _src(*items):
    return Sources(news=[("T", lambda t: list(items))])


def _titles(conn):
    return [r[0] for r in conn.execute("SELECT title FROM news_items ORDER BY id")]


def test_distinct_filings_same_company_both_stored(conn):
    a = RawItem("SEC EDGAR", "https://sec.example/a", "NVIDIA CORP files 8-K (2026-10-10)", "",
                "2026-10-10T00:00:00Z", ("NVDA",))
    b = RawItem("SEC EDGAR", "https://sec.example/b", "NVIDIA CORP files 8-K (2026-10-11)", "",
                "2026-10-11T00:00:00Z", ("NVDA",))
    refresh_news(conn, _src(a, b), HeuristicScorer(), NOW)
    assert _count(conn, "SELECT COUNT(*) FROM news_items") == 2


def test_same_generic_title_days_apart_both_stored(conn):
    a = RawItem("RSS", "https://r.example/1", "Markets wrap", "", "2026-10-06T10:00:00Z")
    b = RawItem("RSS", "https://r.example/2", "Markets wrap", "", "2026-10-11T10:00:00Z")
    out = refresh_news(conn, _src(a, b), HeuristicScorer(), NOW)
    assert _count(conn, "SELECT COUNT(*) FROM news_items") == 2 and out["duplicates"] == 0


def test_same_title_within_window_merges_tickers(conn):
    a = RawItem("A", "https://a.example/1", "Chip rally lifts stocks", "",
                "2026-10-12T10:00:00Z", ("NVDA",))
    b = RawItem("B", "https://b.example/9", "Chip rally lifts stocks", "",
                "2026-10-12T12:00:00Z", ("TSM",))
    out = refresh_news(conn, _src(a, b), HeuristicScorer(), NOW)
    assert out["duplicates"] == 1 and _count(conn, "SELECT COUNT(*) FROM news_items") == 1
    tickers = json.loads(conn.execute("SELECT tickers FROM news_items").fetchone()[0])
    assert tickers == ["NVDA", "TSM"]
    assert _count(conn, "SELECT COUNT(*) FROM news_scores") == 2


def _hold(conn, ticker, name):
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("INSERT INTO securities (security_id, ticker, name) VALUES (?,?,?)",
                 (ticker, ticker, name))
    conn.execute("INSERT INTO holdings (account_id, security_id, value) VALUES ('a',?,1)",
                 (ticker,))


def test_aliases_strip_punctuation_and_skip_common_words(conn):
    _hold(conn, "TGT", "Target Corp.")
    _hold(conn, "AAPL", "Apple Inc.")
    _hold(conn, "AMD", "Advanced Micro Devices Inc")
    sec = tracked_securities(conn)
    assert sec["TGT"] == ("target corp",)
    assert sec["AAPL"] == ("apple inc",)
    assert sec["AMD"] == ("advanced micro devices inc", "advanced micro devices")
    price = RawItem("s", "u", "Analyst lifts price target on chip maker", "", "t")
    assert tag_tickers(price, sec) == []
    assert tag_tickers(RawItem("s", "u", "Apple Inc. unveils phone", "", "t"), sec) == ["AAPL"]


def test_scorer_exception_is_contained(conn):
    class Boom:
        def score(self, *a):
            raise RuntimeError("secret body")

    out = refresh_news(conn, fixture_sources(NOW), Boom(), NOW, fallback=HeuristicScorer())
    assert out["unscored"] == 0 and out["scored"] > 0
    out2 = refresh_news(conn, _src(), Boom(), NOW)
    assert out2["scored"] == 0


def test_fixture_timestamps_use_z_format():
    import re
    srcs = fixture_sources(NOW)
    stamps = [i.published_at for _, f in srcs.news for i in f([])]
    assert stamps and all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", s) for s in stamps)


def test_market_placeholder_dropped_when_real_ticker_merges(conn):
    a = RawItem("A", "https://a.example/1", "Stocks drift higher", "", "2026-10-12T10:00:00Z")
    b = RawItem("B", "https://b.example/9", "Stocks drift higher", "",
                "2026-10-12T12:00:00Z", ("NVDA",))
    refresh_news(conn, _src(a), HeuristicScorer(), NOW)
    news_id = conn.execute("SELECT id FROM news_items").fetchone()[0]
    assert _count(conn, f"SELECT COUNT(*) FROM news_scores WHERE news_id={news_id} "
                        f"AND ticker='{MARKET}'") == 1
    out = refresh_news(conn, _src(b), HeuristicScorer(), NOW)
    assert out["duplicates"] == 1
    tickers = json.loads(conn.execute("SELECT tickers FROM news_items").fetchone()[0])
    assert tickers == ["NVDA"]
    assert _count(conn, f"SELECT COUNT(*) FROM news_scores WHERE news_id={news_id} "
                        f"AND ticker='{MARKET}'") == 0
