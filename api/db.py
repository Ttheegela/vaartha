"""SQLite connection and schema setup (stdlib sqlite3, WAL mode)."""

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
TABLES = (
    "items", "accounts", "transactions", "securities", "holdings", "recurring_streams",
    "budgets", "goals", "networth_snapshots", "news_items", "news_scores", "alerts",
    "briefings", "agent_messages",
)
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
    conn.commit()
