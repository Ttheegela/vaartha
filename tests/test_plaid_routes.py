"""Plaid routes with FakePlaid injected; configuration errors."""

import json
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from api.crypto import new_key
from api.main import LINK_EVENT_RATE, create_app
from api.plaid_client import PlaidClient
from api.plaid_fake import FAKE_ACCESS_TOKEN, FAKE_INSTITUTION_ID, FAKE_ITEM_ID, FakePlaid
from api.settings import Settings
from core.regime import compute_regime

TODAY = date(2026, 10, 12)
NORMAL = compute_regime([100.0] * 40, [100.0] * 40, [1800.0] * 40)


def _app(tmp_path, plaid=None, **settings_kw):
    s = Settings(db_path=tmp_path / "v.db", instance="demo", **settings_kw)
    app = create_app(s, regime_provider=lambda: NORMAL, today=lambda: TODAY, plaid=plaid)
    return TestClient(app)


def test_not_configured_is_503(tmp_path):
    c = _app(tmp_path)
    for path in ("/api/plaid/link_token", "/api/sync"):
        r = c.post(path)
        assert r.status_code == 503 and r.json() == {"detail": "plaid not configured"}


def test_configured_without_key_refuses_to_start(tmp_path):
    with pytest.raises(ValueError, match="TOKEN_ENCRYPTION_KEY"):
        _app(tmp_path, plaid_client_id="c", plaid_secret="s")


def test_link_exchange_sync_flow(tmp_path):
    fake = FakePlaid(TODAY)
    c = _app(tmp_path, plaid=fake, token_key=new_key())
    assert c.post("/api/plaid/link_token").json() == {"link_token": "link-fake-1"}
    assert c.post("/api/plaid/exchange", json={"public_token": "public-fake-1"}).json() == {
        "item_id": FAKE_ITEM_ID}
    assert len(c.get("/api/accounts").json()["accounts"]) == 4
    assert c.post("/api/sync").json() == {"items": {FAKE_ITEM_ID: "ok"}}


def test_sync_reports_per_item_error_not_500(tmp_path):
    fake = FakePlaid(TODAY)
    c = _app(tmp_path, plaid=fake, token_key=new_key())
    c.post("/api/plaid/exchange", json={"public_token": "public-fake-1"})
    fake.fail_next["accounts_get"] = "ITEM_LOGIN_REQUIRED"
    r = c.post("/api/sync")
    assert r.status_code == 200
    assert r.json() == {"items": {FAKE_ITEM_ID: "ITEM_LOGIN_REQUIRED"}}


def test_exchange_plaid_error_is_502(tmp_path):
    fake = FakePlaid(TODAY)
    fake.fail_next["exchange_public_token"] = "INVALID_PUBLIC_TOKEN"
    c = _app(tmp_path, plaid=fake, token_key=new_key())
    r = c.post("/api/plaid/exchange", json={"public_token": "bad"})
    assert r.status_code == 502 and r.json() == {"detail": "INVALID_PUBLIC_TOKEN"}


def test_exchange_ok_even_if_first_sync_fails(tmp_path):
    fake = FakePlaid(TODAY)
    fake.fail_next["accounts_get"] = "INTERNAL_SERVER_ERROR"
    c = _app(tmp_path, plaid=fake, token_key=new_key())
    r = c.post("/api/plaid/exchange", json={"public_token": "public-fake-1"})
    assert r.status_code == 200 and r.json() == {"item_id": FAKE_ITEM_ID}
    assert c.get("/api/accounts").json()["items"][0]["item_id"] == FAKE_ITEM_ID


def test_exchange_malformed_plaid_body_is_502(tmp_path):
    client = PlaidClient("sandbox", "c", "s",
                         transport=httpx.MockTransport(lambda req: httpx.Response(200, json={})))
    c = _app(tmp_path, plaid=client, token_key=new_key())
    r = c.post("/api/plaid/exchange", json={"public_token": "p"})
    assert r.status_code == 502 and r.json() == {"detail": "PLAID_BAD_RESPONSE"}


def test_sync_survives_failing_recurring_refresh(tmp_path, monkeypatch):
    fake = FakePlaid(TODAY)
    c = _app(tmp_path, plaid=fake, token_key=new_key())
    c.post("/api/plaid/exchange", json={"public_token": "public-fake-1"})

    def boom(conn, today):
        raise RuntimeError("x")

    monkeypatch.setattr("api.sync.refresh_recurring", boom)
    r = c.post("/api/sync")
    assert r.status_code == 200 and r.json() == {"items": {FAKE_ITEM_ID: "ok"}}


def test_demo_admin_endpoints_rate_limited(tmp_path):
    c = _app(tmp_path, plaid=FakePlaid(TODAY), token_key=new_key())
    for _ in range(5):
        assert c.post("/api/plaid/link_token").status_code == 200
    for path in ("/api/plaid/link_token", "/api/sync", "/api/plaid/exchange"):
        r = c.post(path, json={"public_token": "public-fake-1"})
        assert r.status_code == 429 and r.json() == {"detail": "rate limit: 5 per hour"}


def test_owner_admin_endpoints_not_limited(tmp_path):
    s = Settings(db_path=tmp_path / "v.db", instance="owner", token_key=new_key())
    c = TestClient(create_app(s, regime_provider=lambda: NORMAL, today=lambda: TODAY,
                              plaid=FakePlaid(TODAY)))
    assert all(c.post("/api/plaid/link_token").status_code == 200 for _ in range(8))


REDIRECT = "https://mac.tail.ts.net/oauth-return"


def test_link_token_consents_investments_and_passes_redirect_uri(tmp_path):
    fake = FakePlaid(TODAY)
    c = _app(tmp_path, plaid=fake, token_key=new_key(), plaid_redirect_uri=REDIRECT)
    assert c.post("/api/plaid/link_token").status_code == 200
    call = fake.link_calls[-1]
    assert call["products"] == ["transactions"]
    assert call["additional_consented"] == ["investments"]
    assert call["redirect_uri"] == REDIRECT and call["access_token"] is None


def test_update_mode_link_token_for_item(tmp_path):
    fake = FakePlaid(TODAY)
    c = _app(tmp_path, plaid=fake, token_key=new_key(), plaid_redirect_uri=REDIRECT)
    c.post("/api/plaid/exchange", json={"public_token": "public-fake-1"})
    r = c.post("/api/plaid/link_token", json={"item_id": FAKE_ITEM_ID})
    assert r.status_code == 200 and r.json() == {"link_token": "link-fake-1"}
    call = fake.link_calls[-1]
    assert call["access_token"] == FAKE_ACCESS_TOKEN and call["redirect_uri"] == REDIRECT
    assert FAKE_ACCESS_TOKEN not in r.text


def test_update_mode_unknown_item_is_404(tmp_path):
    c = _app(tmp_path, plaid=FakePlaid(TODAY), token_key=new_key())
    r = c.post("/api/plaid/link_token", json={"item_id": "nope"})
    assert r.status_code == 404


def test_link_event_logged_as_json_without_tokens(tmp_path, capsys):
    c = _app(tmp_path, plaid=FakePlaid(TODAY), token_key=new_key())
    r = c.post("/api/plaid/link_event", json={
        "event": "EXIT", "link_session_id": "sess-1", "institution_id": "ins_3",
        "error_type": "ITEM_ERROR", "error_code": "INVALID_CREDENTIALS",
        "public_token": "public-secret-1", "link_token": "link-secret-1"})
    assert r.status_code == 204
    lines = [json.loads(x) for x in capsys.readouterr().err.splitlines() if "plaid_link" in x]
    payload = json.loads(lines[-1]["msg"])
    assert payload == {"event": "EXIT", "link_session_id": "sess-1", "institution_id": "ins_3",
                       "error_type": "ITEM_ERROR", "error_code": "INVALID_CREDENTIALS",
                       "view_name": None, "request_id": None}
    assert "secret" not in json.dumps(lines)


def test_link_event_rejects_oversized_fields(tmp_path):
    c = _app(tmp_path, plaid=FakePlaid(TODAY), token_key=new_key())
    assert c.post("/api/plaid/link_event", json={"event": "x" * 500}).status_code == 422


def test_link_event_has_its_own_demo_limit(tmp_path):
    c = _app(tmp_path, plaid=FakePlaid(TODAY), token_key=new_key())
    codes = [c.post("/api/plaid/link_event", json={"event": "OPEN"}).status_code
             for _ in range(LINK_EVENT_RATE + 1)]
    assert codes[:LINK_EVENT_RATE] == [204] * LINK_EVENT_RATE and codes[-1] == 429
    assert c.post("/api/plaid/link_token").status_code == 200  # admin limit untouched


def test_exchange_refuses_duplicate_institution(tmp_path):
    fake = FakePlaid(TODAY)
    c = _app(tmp_path, plaid=fake, token_key=new_key())
    c.post("/api/plaid/exchange", json={"public_token": "public-fake-1"})
    fake.fail_next["exchange_public_token"] = "SHOULD_NOT_BE_CALLED"
    r = c.post("/api/plaid/exchange",
               json={"public_token": "public-fake-2", "institution_id": FAKE_INSTITUTION_ID})
    assert r.status_code == 409 and r.json() == {"detail": "institution already linked"}
    assert len(c.get("/api/accounts").json()["items"]) == 1


def test_update_mode_refused_for_removed_item(tmp_path):
    fake = FakePlaid(TODAY)
    c = _app(tmp_path, plaid=fake, token_key=new_key())
    c.post("/api/plaid/exchange", json={"public_token": "public-fake-1"})
    fake.fail_next["accounts_get"] = "ITEM_NOT_FOUND"
    c.post("/api/sync")
    r = c.post("/api/plaid/link_token", json={"item_id": FAKE_ITEM_ID})
    assert r.status_code == 409
