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


def test_news_keys_from_env_hidden(monkeypatch, tmp_path):
    for k, v in {"ALPACA_API_KEY": "ak", "ALPACA_SECRET_KEY": "as", "FINNHUB_API_KEY": "fk",
                 "TYPESAFE_API_KEY": "tk", "SEC_USER_AGENT": "Varta dev@example.com"}.items():
        monkeypatch.setenv(k, v)
    s = Settings.from_env()
    assert (s.alpaca_key, s.alpaca_secret, s.finnhub_key, s.typesafe_key, s.sec_user_agent) == (
        "ak", "as", "fk", "tk", "Varta dev@example.com")
    assert "ak" not in repr(s) and "tk" not in repr(s)


def test_llm_settings_from_env(monkeypatch, tmp_path):
    for k in ("LLM_BASE_URL", "LLM_MODEL", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert not Settings.from_env().llm_configured
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    assert not Settings.from_env().llm_configured
    monkeypatch.setenv("LLM_MODEL", "qwen3")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret-xyz")
    s = Settings.from_env()
    assert (s.llm_base_url, s.llm_model, s.llm_api_key) == (
        "http://localhost:11434/v1", "qwen3", "sk-secret-xyz")
    assert s.llm_configured
    assert "sk-secret-xyz" not in repr(s)


def test_chat_rate_proxy_tz_from_env(monkeypatch):
    for k in ("CHAT_RATE_PER_HOUR", "TRUST_PROXY", "VARTA_TZ"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("VARTA_INSTANCE", "demo")
    s = Settings.from_env()
    assert (s.chat_rate_per_hour, s.trust_proxy, s.tz) == (20, False, "America/New_York")
    monkeypatch.setenv("VARTA_INSTANCE", "owner")
    assert Settings.from_env().chat_rate_per_hour == 0
    monkeypatch.setenv("CHAT_RATE_PER_HOUR", "5")
    monkeypatch.setenv("TRUST_PROXY", "1")
    monkeypatch.setenv("VARTA_TZ", "UTC")
    s = Settings.from_env()
    assert (s.chat_rate_per_hour, s.trust_proxy, s.tz) == (5, True, "UTC")
