"""Worker tick with a fake runner."""

from contextlib import closing
from datetime import UTC, datetime

from api.db import connect, init_db
from api.settings import Settings
from worker.main import tick

NOW = datetime(2026, 10, 12, 18, 0, tzinfo=UTC)


def settings(tmp_path, instance="demo"):
    s = Settings(db_path=tmp_path / "w.db", instance=instance)
    with closing(connect(s.db_path)) as c:
        init_db(c)
    return s


def test_runs_due_and_records(tmp_path):
    s, ran = settings(tmp_path), []
    names = tick(s, NOW, runner=lambda n, st, now: ran.append(n))
    assert names == ran and set(names) == {"sync", "news", "alerts", "briefing", "backup",
                                           "demo_reset"}
    with closing(connect(s.db_path)) as c:
        keys = {r[0] for r in c.execute("SELECT key FROM app_state WHERE key LIKE 'job:%'")}
    assert keys == {f"job:{n}" for n in names}
    assert tick(s, NOW, runner=lambda n, st, now: ran.append(n)) == []


def test_failure_isolated_and_recorded(tmp_path, caplog):
    s = settings(tmp_path)

    def runner(n, st, now):
        if n == "news":
            raise RuntimeError("x")

    names = tick(s, NOW, runner=runner)
    assert "news" in names and "alerts" in names
    with closing(connect(s.db_path)) as c:
        assert c.execute("SELECT 1 FROM app_state WHERE key='job:news'").fetchone()
    assert any(r.exc_info for r in caplog.records)
    assert tick(s, NOW, runner=runner) == []


def test_demo_reset_skipped_on_owner(tmp_path):
    names = tick(settings(tmp_path, "owner"), NOW, runner=lambda *a: None)
    assert "demo_reset" not in names and "backup" in names
