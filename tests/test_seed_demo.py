"""Offline demo seed is complete and idempotent."""

from datetime import date

from api.crypto import new_key
from api.db import connect
from api.plaid_fake import FakePlaid
from api.settings import Settings
from scripts.seed_demo import DEMO_BUDGETS, seed

TODAY = date(2026, 10, 12)


def test_fake_seed_twice(tmp_path):
    s = Settings(db_path=tmp_path / "v.db", instance="demo", token_key=new_key())
    seed(s, "fake", TODAY)
    seed(s, "fake", TODAY)
    conn = connect(s.db_path)
    count = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731
    assert count("items") == 1
    assert count("budgets") == len(DEMO_BUDGETS)
    assert count("goals") == 3
    assert count("recurring_streams") >= 7


def test_seed_requires_key(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="TOKEN_ENCRYPTION_KEY"):
        seed(Settings(db_path=tmp_path / "v.db", instance="demo"), "fake", TODAY)


def test_seed_fails_when_first_sync_fails(tmp_path):
    import pytest
    s = Settings(db_path=tmp_path / "v.db", instance="demo", token_key=new_key())
    plaid = FakePlaid(TODAY)
    plaid.fail_next["accounts_get"] = "INTERNAL_SERVER_ERROR"
    with pytest.raises(RuntimeError, match="first sync failed"):
        seed(s, "fake", TODAY, plaid)
    assert connect(s.db_path).execute("SELECT COUNT(*) FROM goals").fetchone()[0] == 0
