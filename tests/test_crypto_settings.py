"""Token encryption and Plaid settings."""

import pytest
from cryptography.fernet import InvalidToken

from api.crypto import TokenBox, new_key
from api.settings import Settings


def test_seal_open_roundtrip():
    box = TokenBox(new_key())
    blob = box.seal("access-sandbox-123")
    assert b"access-sandbox-123" not in blob
    assert box.open(blob) == "access-sandbox-123"


def test_wrong_key_cannot_open():
    blob = TokenBox(new_key()).seal("access-sandbox-123")
    with pytest.raises(InvalidToken):
        TokenBox(new_key()).open(blob)


def test_secrets_hidden_from_repr(tmp_path):
    s = Settings(tmp_path / "v.db", "owner", "sandbox", "client-abc", "secret-xyz", "key-123")
    text = repr(s)
    assert "secret-xyz" not in text and "client-abc" not in text and "key-123" not in text


def test_plaid_configured_needs_both_credentials(tmp_path):
    assert not Settings(tmp_path / "v.db", "demo").plaid_configured
    assert not Settings(tmp_path / "v.db", "demo", plaid_client_id="c").plaid_configured
    both = Settings(tmp_path / "v.db", "demo", plaid_client_id="c", plaid_secret="s")
    assert both.plaid_configured


def test_demo_cannot_use_production(tmp_path):
    with pytest.raises(ValueError, match="demo"):
        Settings(tmp_path / "v.db", "demo", plaid_env="production")


def test_unknown_plaid_env_rejected(monkeypatch):
    monkeypatch.setenv("PLAID_ENV", "development")
    with pytest.raises(ValueError, match="PLAID_ENV"):
        Settings.from_env()


def test_from_env_reads_plaid(monkeypatch, tmp_path):
    monkeypatch.setenv("VARTA_DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("VARTA_INSTANCE", "owner")
    monkeypatch.setenv("PLAID_ENV", "production")
    monkeypatch.setenv("PLAID_CLIENT_ID", "cid")
    monkeypatch.setenv("PLAID_SECRET", "sec")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "k")
    s = Settings.from_env()
    assert (s.plaid_env, s.plaid_client_id, s.plaid_secret, s.token_key) == (
        "production", "cid", "sec", "k")
