"""In-place demo reset."""

from contextlib import closing
from datetime import UTC, date, datetime

import pytest

from api.crypto import new_key
from api.db import connect
from api.settings import Settings
from scripts.reset_demo import reset
from scripts.seed_demo import seed

TODAY = date(2026, 10, 12)


def count(conn, t):
    return conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]


def test_reset_reseeds(tmp_path):
    s = Settings(db_path=tmp_path / "v.db", instance="demo", token_key=new_key())
    seed(s, "fake", TODAY)
    with closing(connect(s.db_path)) as c:
        c.execute("INSERT INTO agent_messages (conversation_id, role, content) "
                  "VALUES ('c','user','hi')")
        c.execute("INSERT INTO app_state (key, value) VALUES ('job:x','1')")
        c.commit()
    out = reset(s, TODAY, now=datetime(2026, 10, 12, 7, tzinfo=UTC))
    assert out["source"] == "fake" and out["briefing"] is False
    with closing(connect(s.db_path)) as c:
        assert count(c, "agent_messages") == 0
        assert count(c, "accounts") == 4
        assert c.execute("SELECT 1 FROM app_state WHERE key='job:x'").fetchone()


def test_owner_refused(tmp_path):
    with pytest.raises(ValueError):
        reset(Settings(db_path=tmp_path / "v.db", instance="owner"), TODAY)
