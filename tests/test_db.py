"""SQLite helpers: schema, WAL, idempotent init, settings."""

import pytest

from api.db import TABLES, connect, init_db
from api.settings import Settings


def test_init_creates_all_tables(tmp_path):
    conn = connect(tmp_path / "v.db")
    init_db(conn)
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(TABLES) <= names


def test_wal_and_foreign_keys(tmp_path):
    conn = connect(tmp_path / "v.db")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_missing_parent_dir_is_created(tmp_path):
    path = tmp_path / "fresh" / "volume" / "v.db"
    init_db(connect(path))
    assert path.exists()


def test_init_twice_keeps_rows(tmp_path):
    path = tmp_path / "v.db"
    conn = connect(path)
    init_db(conn)
    conn.execute("INSERT INTO budgets VALUES ('FOOD_AND_DRINK', 600)")
    conn.commit()
    init_db(connect(path))
    assert conn.execute("SELECT monthly_limit FROM budgets").fetchone()[0] == 600


def test_settings_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("VARTA_DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("VARTA_INSTANCE", "owner")
    s = Settings.from_env()
    assert s.db_path == tmp_path / "x.db"
    assert s.instance == "owner"


def test_settings_rejects_unknown_instance(monkeypatch):
    monkeypatch.setenv("VARTA_INSTANCE", "prod")
    with pytest.raises(ValueError, match="VARTA_INSTANCE"):
        Settings.from_env()


def test_news_columns_and_crowd_odds(tmp_path):
    conn = connect(tmp_path / "v.db")
    init_db(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(news_scores)")}
    assert {"channel", "scored_by"} <= cols
    assert conn.execute("SELECT COUNT(*) FROM crowd_odds").fetchone()[0] == 0


def test_migration_adds_columns_to_old_db(tmp_path):
    conn = connect(tmp_path / "v.db")
    conn.execute(
        "CREATE TABLE news_scores (news_id INTEGER, ticker TEXT, PRIMARY KEY (news_id, ticker))"
    )
    conn.commit()
    init_db(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(news_scores)")}
    assert {"channel", "scored_by"} <= cols
