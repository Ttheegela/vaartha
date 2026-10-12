"""In-place demo reset."""

from contextlib import closing
from datetime import UTC, date, datetime

import pytest

import scripts.reset_demo as rd
from api.agent_tools import build_toolbox
from api.crypto import new_key
from api.db import connect
from api.settings import Settings
from core.regime import Regime
from scripts.reset_demo import reset
from scripts.seed_demo import seed

TODAY = date(2026, 10, 12)
NORMAL = Regime("Normal", 0.1, 0.2, -0.01, 80.0, {})


def _offline_toolbox(monkeypatch):
    def no_prices(_tickers):
        raise RuntimeError("no network")

    monkeypatch.setattr(rd, "default_toolbox", lambda settings, today: build_toolbox(
        settings.db_path, today, lambda: NORMAL, no_prices))


def count(conn, t):
    return conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]


def test_reset_reseeds(tmp_path, monkeypatch):
    _offline_toolbox(monkeypatch)
    s = Settings(db_path=tmp_path / "v.db", instance="demo", token_key=new_key())
    seed(s, "fake", TODAY)
    with closing(connect(s.db_path)) as c:
        c.execute("INSERT INTO agent_messages (conversation_id, role, content) "
                  "VALUES ('c','user','hi')")
        c.execute("INSERT INTO app_state (key, value) VALUES ('job:x','1')")
        c.commit()
    out = reset(s, TODAY, now=datetime(2026, 10, 12, 7, tzinfo=UTC))
    assert out["source"] == "fake" and out["briefing"] is False
    assert isinstance(out["alerts"], int) and out["alerts"] >= 0 and out["news"] is not None
    with closing(connect(s.db_path)) as c:
        assert count(c, "agent_messages") == 0
        assert count(c, "accounts") == 4
        assert c.execute("SELECT 1 FROM app_state WHERE key='job:x'").fetchone()


def test_owner_refused(tmp_path):
    with pytest.raises(ValueError):
        reset(Settings(db_path=tmp_path / "v.db", instance="owner"), TODAY)


def test_failed_sandbox_seed_leaves_no_partial_rows(tmp_path, monkeypatch):
    _offline_toolbox(monkeypatch)
    real = rd.seed

    def flaky(settings, source, today):
        if source == "sandbox":
            with closing(connect(settings.db_path)) as c:
                c.execute("INSERT INTO items (item_id, access_token_enc, institution) "
                          "VALUES ('partial', x'00', 'x')")
                c.commit()
            raise RuntimeError("sandbox down")
        return real(settings, source, today)

    monkeypatch.setattr(rd, "seed", flaky)
    s = Settings(db_path=tmp_path / "v.db", instance="demo", token_key=new_key(),
                 plaid_client_id="id", plaid_secret="sec")
    assert reset(s, TODAY, now=datetime(2026, 10, 12, 7, tzinfo=UTC))["source"] == "fake"
    with closing(connect(s.db_path)) as c:
        assert count(c, "items") == 1
        assert c.execute("SELECT 1 FROM items WHERE item_id='partial'").fetchone() is None
