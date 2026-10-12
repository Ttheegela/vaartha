"""Pure schedule logic."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from worker.schedule import JOBS, Job, due

NY = ZoneInfo("America/New_York")
EVERY = Job("n", every=timedelta(minutes=15))
AT = Job("b", at=time(7, 0))


def utc(y, m, d, h, mi=0, s=0):
    return datetime(y, m, d, h, mi, s, tzinfo=UTC)


def local(y, m, d, h, mi=0, s=0):
    return datetime(y, m, d, h, mi, s, tzinfo=NY).astimezone(UTC)


def test_every():
    now = utc(2026, 10, 12, 12)
    assert due(EVERY, now, None, NY)
    assert not due(EVERY, now, now - timedelta(minutes=5), NY)
    assert due(EVERY, now, now - timedelta(minutes=16), NY)


def test_at():
    yest = local(2026, 10, 11, 7, 0, 30)
    assert not due(AT, local(2026, 10, 12, 6, 59), yest, NY)
    assert due(AT, local(2026, 10, 12, 7, 1), yest, NY)
    assert not due(AT, local(2026, 10, 12, 7, 1), local(2026, 10, 12, 7, 0, 30), NY)
    assert due(AT, local(2026, 10, 12, 7, 1), None, NY)


def test_dst_spring_forward_once():
    last = local(2026, 3, 7, 7, 0, 30)
    assert not due(AT, local(2026, 3, 8, 6, 59), last, NY)
    assert due(AT, local(2026, 3, 8, 7, 1), last, NY)
    assert not due(AT, local(2026, 3, 8, 9), local(2026, 3, 8, 7, 1), NY)


def test_down_three_days_one_run():
    last = local(2026, 10, 9, 7, 0, 30)
    now = local(2026, 10, 12, 8)
    assert due(AT, now, last, NY)
    assert not due(AT, now + timedelta(minutes=1), now, NY)


def test_jobs_table():
    assert [j.name for j in JOBS] == ["sync", "news", "alerts", "briefing", "backup", "demo_reset"]
    assert [j.name for j in JOBS if j.demo_only] == ["demo_reset"]


def test_backup_dst_days_run_once():
    backup = next(j for j in JOBS if j.name == "backup")
    for y, m, d in [(2026, 3, 8), (2026, 11, 1)]:
        last = local(y, m, d, 2, 31) - timedelta(days=1)
        first = utc(y, m, d, 12)  # well after 02:30 local
        assert due(backup, first, last, NY)
        assert not due(backup, first + timedelta(minutes=1), first, NY)
