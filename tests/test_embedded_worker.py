"""Embedded scheduler, boot reseed, CORS and cookie domain."""

import logging
import threading
from contextlib import closing
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from api.db import connect, init_db
from api.main import create_app
from api.settings import Settings
from tests.test_advisor_api import NORMAL, TODAY, FakeLLM, _text
from worker import main as wm

NOW = datetime(2026, 10, 12, 18, 0, tzinfo=UTC)
ORIGIN = "https://demo.example.dev"


def _settings(tmp_path, instance="demo", **kw):
    s = Settings(db_path=tmp_path / "e.db", instance=instance, llm_model="test-model", **kw)
    with closing(connect(s.db_path)) as c:
        init_db(c)
    return s


def _app(s, llm=None):
    return create_app(s, regime_provider=lambda: NORMAL, today=lambda: TODAY, llm=llm)


def _names():
    return {t.name for t in threading.enumerate()}


def test_no_worker_thread_by_default(tmp_path):
    with TestClient(_app(_settings(tmp_path))):
        assert "varta-worker" not in _names()


def test_worker_thread_starts_and_stops(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(wm, "boot_reseed_if_empty", lambda s: calls.append("boot"))
    monkeypatch.setattr(wm, "run_loop", lambda s, stop: calls.append("loop"))
    with TestClient(_app(_settings(tmp_path, run_worker=True))):
        pass
    assert calls == ["boot", "loop"]
    assert "varta-worker" not in _names()


def test_run_loop_ticks_until_stopped(tmp_path, monkeypatch):
    s, stop, seen = _settings(tmp_path), threading.Event(), []
    monkeypatch.setattr(wm, "tick", lambda st, now: seen.append(now) or stop.set())
    wm.run_loop(s, stop, tick_seconds=0, clock=lambda: NOW)
    assert seen == [NOW]


def test_run_loop_survives_tick_error(tmp_path, monkeypatch, caplog):
    s, stop, n = _settings(tmp_path), threading.Event(), []

    def bad(st, now):
        n.append(1)
        if len(n) == 2:
            stop.set()
        raise RuntimeError("boom")

    monkeypatch.setattr(wm, "tick", bad)
    with caplog.at_level(logging.ERROR):
        wm.run_loop(s, stop, tick_seconds=0)
    assert len(n) == 2 and "tick failed" in caplog.text


def test_boot_reseed_empty_demo_then_tick_skips(tmp_path, monkeypatch):
    s, called = _settings(tmp_path), []
    monkeypatch.setattr(wm, "reset", lambda st, today, now=None: called.append(today))
    assert wm.boot_reseed_if_empty(s) is True and len(called) == 1
    ran = []
    names = wm.tick(s, datetime.now(UTC), runner=lambda n, st, now: ran.append(n))
    assert not {"demo_reset", "news", "alerts", "briefing"} & set(names)


def _insert_account(s):
    with closing(connect(s.db_path)) as c:
        c.execute("PRAGMA foreign_keys=OFF")
        cols = [r for r in c.execute("PRAGMA table_info(accounts)") if r["notnull"]]
        vals = [1 if r["type"].upper().startswith(("INT", "REAL")) else "x" for r in cols]
        c.execute(f"INSERT INTO accounts ({','.join(r['name'] for r in cols)}) "
                  f"VALUES ({','.join('?' * len(vals))})", vals)
        c.commit()


def test_boot_reseed_skipped_when_not_empty_or_owner(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(wm, "reset", lambda *a, **k: called.append(1))
    assert wm.boot_reseed_if_empty(_settings(tmp_path, instance="owner")) is False
    demo = _settings(tmp_path)
    _insert_account(demo)
    assert wm.boot_reseed_if_empty(demo) is False and not called


def test_boot_reseed_failure_returns_false(tmp_path, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(wm, "reset", boom)
    with caplog.at_level(logging.ERROR):
        assert wm.boot_reseed_if_empty(_settings(tmp_path)) is False
    assert "boot reseed failed" in caplog.text


def _preflight(client, origin):
    return client.options("/api/chat", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})


def test_cors_allowed_and_unknown(tmp_path):
    c = TestClient(_app(_settings(tmp_path, cors_origins=(ORIGIN,))))
    r = _preflight(c, ORIGIN)
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ORIGIN
    assert r.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in _preflight(c, "https://evil.dev").headers


def test_cors_absent_when_unset(tmp_path):
    c = TestClient(_app(_settings(tmp_path)))
    r = c.get("/healthz", headers={"Origin": ORIGIN})
    assert "access-control-allow-origin" not in r.headers


def test_cors_on_429(tmp_path):
    s = _settings(tmp_path, cors_origins=(ORIGIN,), chat_rate_per_hour=1)
    c = TestClient(_app(s, FakeLLM(_text("hi"))))
    h = {"Origin": ORIGIN}
    assert c.post("/api/chat", json={"message": "a"}, headers=h).status_code == 200
    r = c.post("/api/chat", json={"message": "b"}, headers=h)
    assert r.status_code == 429 and r.headers["access-control-allow-origin"] == ORIGIN


def test_cookie_domain(tmp_path):
    s = _settings(tmp_path, cookie_domain=".example.dev")
    r = TestClient(_app(s, FakeLLM(_text("hi")))).post("/api/chat", json={"message": "a"})
    assert "domain=" in r.headers["set-cookie"].lower()
    assert "example.dev" in r.headers["set-cookie"]
