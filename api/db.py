"""SQLite connection and schema setup (stdlib sqlite3, WAL mode)."""

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
TABLES = (
    "items", "accounts", "transactions", "securities", "holdings", "recurring_streams",
    "budgets", "goals", "networth_snapshots", "news_items", "news_scores", "alerts",
    "briefings", "agent_messages", "crowd_odds", "app_state",
)
MIGRATIONS = [
    ("news_scores", "channel", "TEXT NOT NULL DEFAULT 'news'"),
    ("news_scores", "scored_by", "TEXT"),
]
BUSY_TIMEOUT_MS = 5000


def connect(path: Path) -> sqlite3.Connection:
    """Open the database, creating its directory; WAL + foreign keys on."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if missing. Safe to run repeatedly."""
    conn.executescript(SCHEMA_PATH.read_text())
    _apply_migrations(conn)
    conn.commit()


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a DB was created."""
    for table, column, ddl in MIGRATIONS:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
