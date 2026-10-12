"""Nightly backup."""

import sqlite3
from datetime import UTC, datetime, timedelta

from scripts.backup_db import backup


def test_backup_copy_and_retention(tmp_path):
    db = tmp_path / "v.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE t (a)")
    c.executemany("INSERT INTO t VALUES (?)", [(1,), (2,), (3,)])
    c.commit()
    c.close()
    t0 = datetime(2026, 10, 1, 2, 30, tzinfo=UTC)
    paths = [backup(db, tmp_path / "b", keep=7, now=t0 + timedelta(days=i)) for i in range(9)]
    left = sorted((tmp_path / "b").glob("varta-*.db"))
    assert len(left) == 7 and left[0] == paths[2] and paths[-1].name == "varta-20261009-0230.db"
    assert sqlite3.connect(paths[-1]).execute("SELECT COUNT(*) FROM t").fetchone()[0] == 3
