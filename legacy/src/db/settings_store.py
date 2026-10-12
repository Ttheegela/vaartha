"""
settings_store.py — GeoSentinel Terminal (VARTA)
SQLite-backed persistent settings store using stdlib sqlite3 only.
All settings survive Streamlit session restarts and server reboots.
Keys are namespaced by user_id (defaults to "default" when no OAuth).
"""

import sqlite3
import datetime
from pathlib import Path
from src.utils import log

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "varta_settings.db"


def _get_conn() -> sqlite3.Connection:
    """
    Open (or create) the settings database and ensure the schema exists.

    Returns:
        sqlite3.Connection with row_factory set to Row.
    """
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            user_id    TEXT    NOT NULL,
            key        TEXT    NOT NULL,
            value      TEXT,
            updated_at TEXT    NOT NULL,
            PRIMARY KEY (user_id, key)
        )
    """)
    conn.commit()
    return conn


def get_setting(key: str, default: str | None = None, user_id: str = "default") -> str | None:
    """
    Retrieve a single setting value.

    Args:
        key: Setting name (e.g. "alpaca_api_key").
        default: Value to return if key does not exist.
        user_id: User namespace (defaults to "default"; set to email after OAuth).
    Returns:
        Stored value as str, or default if not found.
    Example:
        key = get_setting("alpaca_api_key", default="")
    """
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT value FROM settings WHERE user_id = ? AND key = ?",
            (user_id, key),
        ).fetchone()
        conn.close()
        return row["value"] if row else default
    except Exception as e:
        log.warning(f"settings_store.get_setting({key!r}) failed: {e}")
        return default


def set_setting(key: str, value: str, user_id: str = "default") -> None:
    """
    Upsert a single setting value.

    Args:
        key: Setting name.
        value: Value to store (always stored as str; caller converts types).
        user_id: User namespace.
    Example:
        set_setting("fred_api_key", "abc123")
    """
    try:
        conn = _get_conn()
        now = datetime.datetime.utcnow().isoformat()
        conn.execute(
            """
            INSERT INTO settings (user_id, key, value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value,
                                                      updated_at = excluded.updated_at
            """,
            (user_id, key, value, now),
        )
        conn.commit()
        conn.close()
        log.info(f"settings_store: set {key!r} for user {user_id!r}")
    except Exception as e:
        log.error(f"settings_store.set_setting({key!r}) failed: {e}")


def get_all_settings(user_id: str = "default") -> dict[str, str]:
    """
    Retrieve all settings for a user as a flat dict.

    Args:
        user_id: User namespace.
    Returns:
        Dict mapping key → value for all stored settings.
    Example:
        prefs = get_all_settings()
    """
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE user_id = ?", (user_id,)
        ).fetchall()
        conn.close()
        return {r["key"]: r["value"] for r in rows}
    except Exception as e:
        log.warning(f"settings_store.get_all_settings() failed: {e}")
        return {}


def delete_setting(key: str, user_id: str = "default") -> None:
    """
    Delete a single setting key.

    Args:
        key: Setting name to remove.
        user_id: User namespace.
    Example:
        delete_setting("alpaca_secret_key")
    """
    try:
        conn = _get_conn()
        conn.execute(
            "DELETE FROM settings WHERE user_id = ? AND key = ?", (user_id, key)
        )
        conn.commit()
        conn.close()
        log.info(f"settings_store: deleted {key!r} for user {user_id!r}")
    except Exception as e:
        log.error(f"settings_store.delete_setting({key!r}) failed: {e}")
