"""Wipe the demo database and reseed it in place (demo instance only).

Run: uv run python -m scripts.reset_demo
"""

import json
import logging
from contextlib import closing
from datetime import UTC, date, datetime

from api.agent import llm_client
from api.agent_tools import default_toolbox
from api.alerts import generate_alerts
from api.briefing import make_briefing
from api.db import TABLES, connect, init_db
from api.settings import Settings
from scripts.refresh_news import run as refresh_news_run
from scripts.seed_demo import seed

log = logging.getLogger("varta.reset")
KEEP_TABLES = ("app_state",)
# children before parents (foreign keys are on)
DELETE_FIRST = ("news_scores", "holdings", "transactions", "recurring_streams")
DELETE_LAST = ("securities", "accounts", "items")


def _wipe(settings: Settings) -> None:
    """Delete all rows except app_state in one transaction, children first."""
    middle = [t for t in TABLES if t not in KEEP_TABLES + DELETE_FIRST + DELETE_LAST]
    with closing(connect(settings.db_path)) as conn:
        init_db(conn)
        with conn:
            for table in (*DELETE_FIRST, *middle, *DELETE_LAST):
                conn.execute(f"DELETE FROM {table}")


def reset(settings: Settings, today: date, now: datetime | None = None) -> dict:
    """Delete all data except app_state, reseed (sandbox, else fake), then refresh derived data."""
    if settings.instance != "demo":
        raise ValueError("reset_demo only runs on the demo instance")
    now = now or datetime.now(UTC)
    _wipe(settings)
    source = "sandbox" if settings.plaid_configured else "fake"
    try:
        seed(settings, source, today)
    except Exception as exc:
        if source == "fake":
            raise
        log.warning("sandbox seed failed (%s); falling back to fake", type(exc).__name__)
        source = "fake"
        _wipe(settings)  # seed() is not atomic; drop partial sandbox rows
        seed(settings, source, today)
    out: dict = {"source": source, "news": None, "alerts": 0, "briefing": False}
    try:
        out["news"] = refresh_news_run(
            settings, offline=not settings.typesafe_key and not settings.alpaca_key, now=now)
    except Exception as exc:
        log.warning("news refresh failed: %s", type(exc).__name__)
    toolbox = default_toolbox(settings, lambda: today)
    try:
        with closing(connect(settings.db_path)) as conn:
            out["alerts"] = generate_alerts(conn, toolbox)
    except Exception as exc:
        log.warning("alerts failed: %s", type(exc).__name__)
    if settings.llm_configured:
        try:
            with closing(connect(settings.db_path)) as conn:
                make_briefing(conn, llm_client(settings), settings.llm_model, toolbox)
            out["briefing"] = True
        except Exception as exc:
            log.warning("briefing failed: %s", type(exc).__name__)
    return out


if __name__ == "__main__":
    cfg = Settings.from_env()
    print(json.dumps(reset(cfg, datetime.now(UTC).astimezone().date()), default=str))
