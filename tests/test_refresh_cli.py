"""Offline refresh CLI and demo seed news."""

from datetime import UTC, datetime

from api.crypto import new_key
from api.db import connect
from api.settings import Settings
from scripts.refresh_news import run
from scripts.seed_demo import seed

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


def test_offline_run_stores_news_and_markets(tmp_path):
    s = Settings(db_path=tmp_path / "v.db", instance="demo")
    out = run(s, offline=True, now=NOW)
    assert out["stored"] > 0
    assert out["markets"] == 3


def test_fake_seed_includes_news(tmp_path):
    s = Settings(db_path=tmp_path / "v.db", instance="demo", token_key=new_key())
    seed(s, "fake", NOW.date())
    n = connect(s.db_path).execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
    assert n > 0
