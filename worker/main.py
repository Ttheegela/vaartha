"""Scheduler loop: runs the jobs in worker.schedule. No broker, just a tick every minute.

Run: uv run python -m worker.main
"""

import logging
import os
import signal
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from api.agent import llm_client
from api.agent_tools import default_toolbox
from api.alerts import generate_alerts
from api.briefing import make_briefing
from api.crypto import TokenBox
from api.db import connect, init_db
from api.logs import setup_logging
from api.plaid_client import PlaidClient
from api.settings import Settings
from api.sync import sync_all
from scripts.backup_db import backup
from scripts.refresh_news import run as refresh_news_run
from scripts.reset_demo import reset
from worker.schedule import JOBS, due

log = logging.getLogger("varta.worker")
TICK_SECONDS = 60
BACKUP_KEEP = 7
STATE_PREFIX = "job:"


def backup_dir() -> Path:
    """Backup directory from VARTA_BACKUP_DIR, default data/backups."""
    return Path(os.environ.get("VARTA_BACKUP_DIR", "data/backups"))


def run_job(name: str, settings: Settings, now: datetime) -> None:
    """Run one named job."""
    today = now.astimezone(ZoneInfo(settings.tz)).date()
    if name == "news":
        refresh_news_run(settings, offline=False, now=now)
    elif name == "backup":
        backup(settings.db_path, backup_dir(), keep=BACKUP_KEEP, now=now)
    elif name == "demo_reset":
        reset(settings, today, now=now)
    elif name == "sync":
        if not settings.plaid_configured or not settings.token_key:
            log.info("sync skipped: plaid not configured")
            return
        plaid = PlaidClient(settings.plaid_env, settings.plaid_client_id, settings.plaid_secret)
        with closing(connect(settings.db_path)) as conn:
            sync_all(conn, plaid, TokenBox(settings.token_key), today)
    elif name == "alerts":
        with closing(connect(settings.db_path)) as conn:
            generate_alerts(conn, default_toolbox(settings, lambda: today))
    elif name == "briefing":
        if not settings.llm_configured:
            log.info("briefing skipped: LLM not configured")
            return
        with closing(connect(settings.db_path)) as conn:
            make_briefing(conn, llm_client(settings), settings.llm_model,
                          default_toolbox(settings, lambda: today))
    else:
        raise ValueError(f"unknown job {name!r}")


def tick(settings: Settings, now: datetime, runner=run_job) -> list[str]:
    """Run every due job once, record its attempt time, and return the names run."""
    tz = ZoneInfo(settings.tz)
    ran = []
    with closing(connect(settings.db_path)) as conn:
        init_db(conn)
        last = {k[len(STATE_PREFIX):]: datetime.fromisoformat(v) for k, v in conn.execute(
            "SELECT key, value FROM app_state WHERE key LIKE ?", (STATE_PREFIX + "%",))}
        for job in JOBS:
            if (job.demo_only and settings.instance != "demo") \
                    or not due(job, now, last.get(job.name), tz):
                continue
            try:
                runner(job.name, settings, now)
            except Exception:  # noqa: BLE001 - one job never stops the others
                log.exception("job %s failed", job.name)
            conn.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
                         (STATE_PREFIX + job.name, now.isoformat()))
            conn.commit()
            ran.append(job.name)
    return ran


def main() -> None:
    """Tick forever; SIGINT/SIGTERM exit cleanly."""
    setup_logging()
    settings = Settings.from_env()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    log.info("worker started instance=%s tz=%s", settings.instance, settings.tz)
    try:
        while True:
            tick(settings, datetime.now(UTC))
            time.sleep(TICK_SECONDS)
    except KeyboardInterrupt:
        log.info("worker stopped")


if __name__ == "__main__":
    main()
