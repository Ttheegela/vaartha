"""Passkey lock (owner only): setup code, WebAuthn ceremonies (faked verify), sessions, CLI."""

import json
import re
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse

import api.auth as auth
from api.crypto import new_key
from api.db import connect, init_db
from api.main import create_app
from api.plaid_fake import FakePlaid
from api.settings import Settings
from core.regime import compute_regime
from scripts import passkey as cli

TODAY = date(2026, 10, 14)
NORMAL = compute_regime([100.0] * 40, [100.0] * 40, [1800.0] * 40)
RP_ID = "mac.tail.ts.net"
ORIGIN = "https://mac.tail.ts.net"
T0 = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
CRED_ID = b"cred-1"
PUBLIC_KEY = b"public-key-bytes"


class Clock:
    """Mutable fake UTC clock."""

    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


class FakeLLM:
    def __init__(self):
        msg = NS(content="ok", tool_calls=None)
        resp = NS(choices=[NS(message=msg)], usage=NS(prompt_tokens=1, completion_tokens=1))
        self.chat = NS(completions=NS(create=lambda **kw: resp))


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(auth, "_now", c)
    return c


@pytest.fixture
def fake_verify(monkeypatch):
    """Replace py_webauthn verification; record what the server asked it to check."""
    calls = {"reg": [], "auth": []}

    def reg(**kw):
        calls["reg"].append(kw)
        return NS(credential_id=CRED_ID, credential_public_key=PUBLIC_KEY, sign_count=0)

    def authn(**kw):
        calls["auth"].append(kw)
        if calls.get("auth_fail"):
            raise InvalidAuthenticationResponse("bad signature")
        return NS(new_sign_count=kw["credential_current_sign_count"] + 1)

    monkeypatch.setattr(auth, "_verify_registration", reg)
    monkeypatch.setattr(auth, "_verify_authentication", authn)
    return calls


def _settings(tmp_path, instance="owner", **kw):
    if instance == "owner":
        kw.setdefault("passkey_rp_id", RP_ID)
        kw.setdefault("passkey_origin", ORIGIN)
    return Settings(db_path=tmp_path / "v.db", instance=instance, token_key=new_key(),
                    llm_model="test-model", **kw)


def _client(tmp_path, instance="owner", **kw):
    s = _settings(tmp_path, instance, **kw)
    app = create_app(s, regime_provider=lambda: NORMAL, today=lambda: TODAY,
                     plaid=FakePlaid(TODAY), llm=FakeLLM())
    return TestClient(app, base_url="https://testserver"), s


def _client_data(kind, challenge):
    data = {"type": kind, "challenge": challenge, "origin": ORIGIN}
    return bytes_to_base64url(json.dumps(data).encode())


def _reg_credential(challenge, kind="webauthn.create"):
    cid = bytes_to_base64url(CRED_ID)
    return {"id": cid, "rawId": cid, "type": "public-key",
            "response": {"clientDataJSON": _client_data(kind, challenge),
                         "attestationObject": bytes_to_base64url(b"att"),
                         "transports": ["internal", "hybrid"]}}


def _auth_credential(challenge, cred_id=CRED_ID):
    cid = bytes_to_base64url(cred_id)
    return {"id": cid, "rawId": cid, "type": "public-key",
            "response": {"clientDataJSON": _client_data("webauthn.get", challenge),
                         "authenticatorData": bytes_to_base64url(b"ad"),
                         "signature": bytes_to_base64url(b"sig")}}


def _setup_code(s):
    return auth.issue_setup_code(s.db_path)


def _register(c, s):
    code = _setup_code(s)
    opts = c.post("/api/auth/register/options", json={"setup_code": code})
    assert opts.status_code == 200
    r = c.post("/api/auth/register/verify",
               json={"setup_code": code, "credential": _reg_credential(opts.json()["challenge"])})
    assert r.status_code == 200, r.text
    return r


def _login(c):
    ch = c.post("/api/auth/login/options").json()["challenge"]
    return c.post("/api/auth/login/verify", json={"credential": _auth_credential(ch)})


def _db(s):
    return closing(connect(s.db_path))


# --- settings / startup -------------------------------------------------------------------

def test_owner_requires_auth_by_default(tmp_path):
    assert Settings(db_path=tmp_path / "v.db", instance="owner").auth_required is True
    assert Settings(db_path=tmp_path / "v.db", instance="demo").auth_required is False


def test_from_env_owner_auth_escape_hatch(monkeypatch):
    monkeypatch.setenv("VARTA_INSTANCE", "owner")
    assert Settings.from_env().auth_required is True
    monkeypatch.setenv("OWNER_AUTH", "0")
    assert Settings.from_env().auth_required is False


def test_from_env_reads_passkey_settings(monkeypatch):
    monkeypatch.setenv("VARTA_INSTANCE", "owner")
    monkeypatch.setenv("PASSKEY_RP_ID", RP_ID)
    monkeypatch.setenv("PASSKEY_ORIGIN", ORIGIN)
    monkeypatch.setenv("AUTH_IDLE_MINUTES", "5")
    s = Settings.from_env()
    assert (s.passkey_rp_id, s.passkey_origin, s.auth_idle_minutes) == (RP_ID, ORIGIN, 5)
    assert s.passkey_rp_name == "Vārtā"


@pytest.mark.parametrize("kw", [
    {"passkey_rp_id": None},
    {"passkey_origin": None},
    {"passkey_origin": "http://mac.tail.ts.net"},
    {"passkey_origin": "https://mac.tail.ts.net/path"},
    {"passkey_origin": "https://evil.example"},
])
def test_startup_fails_closed(tmp_path, kw):
    with pytest.raises(ValueError, match="PASSKEY"):
        _client(tmp_path, **kw)


def test_localhost_http_origin_allowed(tmp_path):
    c, _ = _client(tmp_path, passkey_rp_id="localhost", passkey_origin="http://localhost:3000")
    assert c.get("/api/auth/status").json()["auth_required"] is True


def test_owner_auth_off_needs_no_passkey_config(tmp_path):
    c, _ = _client(tmp_path, auth_required=False, passkey_rp_id=None, passkey_origin=None)
    assert c.get("/api/accounts").status_code == 200


# --- status / demo ----------------------------------------------------------------------

def test_status_owner(tmp_path, clock, fake_verify):
    c, s = _client(tmp_path)
    assert c.get("/api/auth/status").json() == {
        "auth_required": True, "authenticated": False, "has_credentials": False}
    _register(c, s)
    assert c.get("/api/auth/status").json() == {
        "auth_required": True, "authenticated": True, "has_credentials": True}


def test_demo_has_no_lock(tmp_path):
    c, _ = _client(tmp_path, instance="demo")
    assert c.get("/api/auth/status").json() == {
        "auth_required": False, "authenticated": False, "has_credentials": False}
    assert c.get("/api/accounts").status_code == 200
    assert c.post("/api/auth/register/options", json={"setup_code": "X"}).status_code == 404
    assert c.post("/api/auth/login/options").status_code == 404


# --- registration ---------------------------------------------------------------------

def test_register_options_needs_valid_code(tmp_path, clock):
    c, s = _client(tmp_path)
    assert c.post("/api/auth/register/options", json={}).status_code == 422
    assert c.post("/api/auth/register/options",
                  json={"setup_code": "ABCD-EFGH"}).status_code == 403  # none issued
    code = _setup_code(s)
    wrong = "AAAA-AAAA" if code != "AAAA-AAAA" else "BBBB-BBBB"
    assert c.post("/api/auth/register/options", json={"setup_code": wrong}).status_code == 403
    clock.advance(minutes=10)
    assert c.post("/api/auth/register/options", json={"setup_code": code}).status_code == 403


def test_register_options_shape(tmp_path, clock):
    c, s = _client(tmp_path)
    code = _setup_code(s)
    r = c.post("/api/auth/register/options", json={"setup_code": code.lower().replace("-", "")})
    assert r.status_code == 200
    o = r.json()
    assert o["rp"] == {"id": RP_ID, "name": "Vārtā"}
    assert o["authenticatorSelection"]["residentKey"] == "required"
    assert o["authenticatorSelection"]["userVerification"] == "required"
    assert o["excludeCredentials"] == []
    with _db(s) as conn:
        row = conn.execute("SELECT kind FROM auth_challenges WHERE challenge=?",
                           (o["challenge"],)).fetchone()
    assert row["kind"] == "register"
    again = c.post("/api/auth/register/options", json={"setup_code": code}).json()
    assert again["user"]["id"] == o["user"]["id"]  # fixed per-instance handle


def test_setup_code_stored_hashed(tmp_path):
    s = _settings(tmp_path)
    with _db(s) as conn:
        init_db(conn)
    code = _setup_code(s)
    with _db(s) as conn:
        stored = conn.execute("SELECT value FROM app_state WHERE key='auth:setup_code'").fetchone()
    assert code not in stored["value"] and code.replace("-", "") not in stored["value"]
    assert re.fullmatch(r"[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}", code)


def test_register_verify_consumes_code_and_checks_settings(tmp_path, clock, fake_verify):
    c, s = _client(tmp_path)
    code = _setup_code(s)
    ch = c.post("/api/auth/register/options", json={"setup_code": code}).json()["challenge"]
    r = c.post("/api/auth/register/verify",
               json={"setup_code": code, "credential": _reg_credential(ch)},
               headers={"origin": "https://evil.example"})
    assert r.status_code == 200
    kw = fake_verify["reg"][0]
    assert kw["expected_rp_id"] == RP_ID and kw["expected_origin"] == ORIGIN
    assert kw["require_user_verification"] is True
    assert bytes_to_base64url(kw["expected_challenge"]) == ch
    with _db(s) as conn:
        cred = conn.execute("SELECT * FROM auth_credentials").fetchone()
        assert conn.execute("SELECT COUNT(*) FROM auth_challenges").fetchone()[0] == 0
    assert cred["credential_id"] == bytes_to_base64url(CRED_ID)
    assert bytes(cred["public_key"]) == PUBLIC_KEY
    assert json.loads(cred["transports"]) == ["internal", "hybrid"]
    # second use of the same code: refused at both steps
    assert c.post("/api/auth/register/options", json={"setup_code": code}).status_code == 403
    r2 = c.post("/api/auth/register/verify",
                json={"setup_code": code, "credential": _reg_credential(ch)})
    assert r2.status_code == 403


def test_register_with_existing_credentials_still_needs_code(tmp_path, clock, fake_verify):
    c, s = _client(tmp_path)
    _register(c, s)  # now authenticated, credentials exist
    assert c.post("/api/auth/register/options", json={"setup_code": ""}).status_code == 403
    code = _setup_code(s)
    o = c.post("/api/auth/register/options", json={"setup_code": code}).json()
    assert [x["id"] for x in o["excludeCredentials"]] == [bytes_to_base64url(CRED_ID)]


def test_register_rejects_unknown_or_login_challenge(tmp_path, clock, fake_verify):
    c, s = _client(tmp_path)
    login_ch = c.post("/api/auth/login/options").json()["challenge"]
    code = _setup_code(s)
    c.post("/api/auth/register/options", json={"setup_code": code})
    r = c.post("/api/auth/register/verify",
               json={"setup_code": code, "credential": _reg_credential(login_ch)})
    assert r.status_code == 400 and fake_verify["reg"] == []


def test_register_challenge_expires(tmp_path, clock, fake_verify):
    c, s = _client(tmp_path)
    code = _setup_code(s)
    ch = c.post("/api/auth/register/options", json={"setup_code": code}).json()["challenge"]
    clock.advance(seconds=auth.CHALLENGE_SECONDS)
    r = c.post("/api/auth/register/verify",
               json={"setup_code": code, "credential": _reg_credential(ch)})
    assert r.status_code == 400 and fake_verify["reg"] == []


# --- login ----------------------------------------------------------------------------

def test_login_sets_strict_cookie_and_updates_sign_count(tmp_path, clock, fake_verify):
    c, s = _client(tmp_path)
    _register(c, s)
    fresh = TestClient(c.app, base_url="https://testserver")
    ch = fresh.post("/api/auth/login/options").json()
    assert ch["userVerification"] == "required" and ch["allowCredentials"] == []
    assert ch["rpId"] == RP_ID
    clock.advance(minutes=1)
    r = fresh.post("/api/auth/login/verify", json={"credential": _auth_credential(ch["challenge"])})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    low = cookie.lower()
    assert cookie.startswith(f"{auth.SESSION_COOKIE}=")
    assert "httponly" in low and "samesite=strict" in low and "secure" in low
    assert "path=/" in low and "max-age" not in low and "expires" not in low
    kw = fake_verify["auth"][0]
    assert kw["expected_rp_id"] == RP_ID and kw["expected_origin"] == ORIGIN
    assert kw["require_user_verification"] is True
    assert kw["credential_public_key"] == PUBLIC_KEY and kw["credential_current_sign_count"] == 0
    with _db(s) as conn:
        row = conn.execute("SELECT sign_count, last_used_at FROM auth_credentials").fetchone()
        tokens = [x[0] for x in conn.execute("SELECT token_hash FROM auth_sessions")]
    assert row["sign_count"] == 1 and row["last_used_at"] == (T0 + timedelta(minutes=1)).isoformat()
    token = fresh.cookies[auth.SESSION_COOKIE]
    assert len(tokens) == 2 and token not in tokens  # stored hashed
    assert fresh.get("/api/accounts").status_code == 200


def test_cookie_not_secure_on_http_localhost(tmp_path, clock, fake_verify):
    c, s = _client(tmp_path, passkey_rp_id="localhost", passkey_origin="http://localhost:3000")
    code = _setup_code(s)
    ch = c.post("/api/auth/register/options", json={"setup_code": code}).json()["challenge"]
    r = c.post("/api/auth/register/verify",
               json={"setup_code": code, "credential": _reg_credential(ch)})
    assert "secure" not in r.headers["set-cookie"].lower()


def test_login_challenge_single_use(tmp_path, clock, fake_verify):
    c, s = _client(tmp_path)
    _register(c, s)
    ch = c.post("/api/auth/login/options").json()["challenge"]
    body = {"credential": _auth_credential(ch)}
    assert c.post("/api/auth/login/verify", json=body).status_code == 200
    assert c.post("/api/auth/login/verify", json=body).status_code == 401


def test_login_challenge_expires(tmp_path, clock, fake_verify):
    c, s = _client(tmp_path)
    _register(c, s)
    ch = c.post("/api/auth/login/options").json()["challenge"]
    clock.advance(seconds=auth.CHALLENGE_SECONDS)
    assert c.post("/api/auth/login/verify",
                  json={"credential": _auth_credential(ch)}).status_code == 401


def test_login_unknown_credential_and_failed_verify(tmp_path, clock, fake_verify):
    c, s = _client(tmp_path)
    _register(c, s)
    ch = c.post("/api/auth/login/options").json()["challenge"]
    r = c.post("/api/auth/login/verify", json={"credential": _auth_credential(ch, b"other")})
    assert r.status_code == 401
    fake_verify["auth_fail"] = True
    assert _login(c).status_code == 401
    assert c.post("/api/auth/login/verify", json={"credential": {"id": "x"}}).status_code == 401


# --- middleware / sessions ------------------------------------------------------------

LOCKED = [("get", "/api/accounts", None), ("post", "/api/chat", {"message": "hi"}),
          ("post", "/api/plaid/link_token", None), ("post", "/api/sync", None),
          ("post", "/api/alerts/1/dismiss", None), ("get", "/api/regime", None),
          ("post", "/api/plaid/link_event", {"event": "OPEN"}),
          ("post", "/api/plaid/exchange", {"public_token": "public-fake-1"}),
          ("get", "/docs", None), ("get", "/openapi.json", None)]


@pytest.mark.parametrize(("method", "path", "body"), LOCKED)
def test_locked_without_session(tmp_path, clock, method, path, body):
    c, _ = _client(tmp_path)
    r = getattr(c, method)(path, json=body) if body else getattr(c, method)(path)
    assert r.status_code == 401 and r.json() == {"detail": "locked"}


def test_open_with_session(tmp_path, clock, fake_verify):
    c, s = _client(tmp_path)
    _register(c, s)
    assert c.get("/api/accounts").status_code == 200
    r = c.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 200 and "event: answer" in r.text
    assert c.post("/api/plaid/link_token").status_code == 200
    assert c.post("/api/sync").status_code == 200
    assert c.get("/healthz").status_code == 200


def test_healthz_and_bogus_cookie(tmp_path, clock):
    c, _ = _client(tmp_path)
    assert c.get("/healthz").status_code == 200
    c.cookies.set(auth.SESSION_COOKIE, "forged")
    assert c.get("/api/accounts").status_code == 401


def test_idle_expiry(tmp_path, clock, fake_verify):
    c, s = _client(tmp_path)
    _register(c, s)
    clock.advance(minutes=14, seconds=59)
    assert c.get("/api/accounts").status_code == 200
    clock.advance(minutes=15)
    assert c.get("/api/accounts").status_code == 401
    with _db(s) as conn:
        assert conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 0


def test_sliding_refresh_and_absolute_cap(tmp_path, clock, fake_verify):
    c, s = _client(tmp_path)
    _register(c, s)
    for _ in range(int(auth.AUTH_MAX_HOURS * 60 / 10) - 1):  # every 10 min up to 11h50
        clock.advance(minutes=10)
        assert c.get("/api/accounts").status_code == 200
    clock.advance(minutes=10)  # 12h after creation
    assert c.get("/api/accounts").status_code == 401


def test_idle_minutes_configurable(tmp_path, clock, fake_verify):
    c, s = _client(tmp_path, auth_idle_minutes=2)
    _register(c, s)
    clock.advance(minutes=2)
    assert c.get("/api/accounts").status_code == 401


def test_logout_invalidates_server_side(tmp_path, clock, fake_verify):
    c, s = _client(tmp_path)
    _register(c, s)
    token = c.cookies[auth.SESSION_COOKIE]
    r = c.post("/api/auth/logout")
    assert r.status_code == 204 and auth.SESSION_COOKIE in r.headers["set-cookie"]
    with _db(s) as conn:
        assert conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 0
    replay = TestClient(c.app, base_url="https://testserver")
    replay.cookies.set(auth.SESSION_COOKIE, token)
    assert replay.get("/api/accounts").status_code == 401
    assert c.get("/api/auth/status").json()["authenticated"] is False


# --- CLI ------------------------------------------------------------------------------

def test_cli_setup_code(tmp_path, capsys):
    s = _settings(tmp_path)
    cli.main(["setup-code"], s)
    out = capsys.readouterr().out
    assert re.fullmatch(r"Setup code \(valid 10 min\): [A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}\n",
                        out)
    code = out.strip().rsplit(" ", 1)[1]
    with _db(s) as conn:
        value = conn.execute("SELECT value FROM app_state WHERE key='auth:setup_code'").fetchone()
    assert code not in value[0]


def test_cli_list_and_reset(tmp_path, clock, fake_verify, capsys, monkeypatch):
    c, s = _client(tmp_path)
    _register(c, s)
    capsys.readouterr()
    cli.main(["list"], s)
    out = capsys.readouterr().out
    assert "1 passkey" in out and T0.date().isoformat() in out
    assert PUBLIC_KEY.hex() not in out and bytes_to_base64url(CRED_ID) not in out
    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    with pytest.raises(SystemExit):
        cli.main(["reset"], s)
    with _db(s) as conn:
        assert conn.execute("SELECT COUNT(*) FROM auth_credentials").fetchone()[0] == 1
    cli.main(["reset", "--yes"], s)
    with _db(s) as conn:
        assert conn.execute("SELECT COUNT(*) FROM auth_credentials").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 0
    assert c.get("/api/accounts").status_code == 401
