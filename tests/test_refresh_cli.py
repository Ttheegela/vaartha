"""Offline refresh CLI and demo seed news."""

from contextlib import closing
from datetime import UTC, datetime

from api.crypto import new_key
from api.db import connect
from api.settings import Settings
from scripts import seed_demo
from scripts.refresh_news import run
from scripts.seed_demo import news_status, seed_news

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


def test_offline_run_stores_news_and_markets(tmp_path):
    s = Settings(db_path=tmp_path / "v.db", instance="demo")
    out = run(s, offline=True, now=NOW)
    assert out["stored"] > 0
    assert out["markets"] == 3


def test_seed_news_populates_db(tmp_path):
    s = Settings(db_path=tmp_path / "v.db", instance="demo", token_key=new_key())
    assert seed_news(s, "fake")["stored"] > 0
    with closing(connect(s.db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0] > 0


def test_seed_news_failure_is_contained(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise TypeError("x")
    monkeypatch.setattr(seed_demo, "refresh_news_run", boom)
    s = Settings(db_path=tmp_path / "v.db", instance="demo")
    assert seed_news(s, "fake") is None
    assert "news refresh failed" in news_status("it1", None)


def test_news_status_warns_when_nothing_fetched():
    empty = {"stored": 0, "fetched": {"Alpaca": 0, "RSS": 0}}
    assert "no news fetched" in news_status("it1", empty)
    assert "WARNING" not in news_status("it1", {"stored": 3, "fetched": {"RSS": 3}})
