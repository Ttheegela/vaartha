"""API: health, regime endpoint, caching and failure handling."""

from fastapi.testclient import TestClient

from api.main import REGIME_TTL_SECONDS, create_app
from api.settings import Settings
from core.regime import compute_regime

NORMAL = compute_regime([100.0] * 40, [100.0] * 40, [1800.0] * 40)


def _client(tmp_path, provider, clock=lambda: 0.0):
    settings = Settings(db_path=tmp_path / "v.db", instance="demo")
    return TestClient(create_app(settings, regime_provider=provider, clock=clock))


def test_healthz(tmp_path):
    r = _client(tmp_path, lambda: NORMAL).get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "instance": "demo"}
    assert (tmp_path / "v.db").exists()


def test_regime_ok(tmp_path):
    r = _client(tmp_path, lambda: NORMAL).get("/api/regime")
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "Normal"
    assert set(body["signals"]) == {"vol_score", "dd_score", "gold_oil_score"}


def test_regime_failure_is_503_not_fake_normal(tmp_path):
    def broken():
        raise ValueError("need >= 30 prices, got 3")

    r = _client(tmp_path, broken).get("/api/regime")
    assert r.status_code == 503
    assert r.json() == {"detail": "regime unavailable"}


def test_regime_is_cached_within_ttl(tmp_path):
    calls = []
    now = [0.0]

    def provider():
        calls.append(1)
        return NORMAL

    client = _client(tmp_path, provider, clock=lambda: now[0])
    client.get("/api/regime")
    client.get("/api/regime")
    assert len(calls) == 1
    now[0] = REGIME_TTL_SECONDS + 1
    client.get("/api/regime")
    assert len(calls) == 2
