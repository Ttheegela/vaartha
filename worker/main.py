"""Scheduler loop: runs the jobs in worker.schedule. No broker, just a tick every minute.

Run: uv run python -m worker.main
"""

import logging
import signal
import threading
from contextlib import closing
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from api.agent import llm_client
from api.agent_tools import default_toolbox
from api.alerts import generate_alerts
from api.briefing import make_briefing
from api.crypto import TokenBox
from api.db import connect, init_db
from api.logs import setup_logging
from api.plaid_client import PlaidClient
from api.settings import Settings, local_today
from api.sync import sync_all
from scripts.backup_db import DEFAULT_KEEP, backup, backup_dir
from scripts.refresh_news import run as refresh_news_run
from scripts.reset_demo import reset
from worker.schedule import JOBS, due

log = logging.getLogger("varta.worker")
TICK_SECONDS = 60
STATE_PREFIX = "job:"
RESEED_JOBS = ("demo_reset", "news", "alerts", "briefing")  # done by reset_demo.reset


def run_job(name: str, settings: Settings, now: datetime) -> None:
    """Run one named job."""
    today = now.astimezone(ZoneInfo(settings.tz)).date()
    if name == "news":
        refresh_news_run(settings, offline=False, now=now)
    elif name == "backup":
        backup(settings.db_path, backup_dir(), keep=DEFAULT_KEEP, now=now)
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


def run_loop(settings: Settings, stop: threading.Event, tick_seconds: int = TICK_SECONDS,
             clock=lambda: datetime.now(UTC)) -> None:
    """Init the DB, then tick until `stop` is set; a failing tick is logged, never fatal."""
    with closing(connect(settings.db_path)) as conn:
        init_db(conn)
    log.info("worker started instance=%s tz=%s", settings.instance, settings.tz)
    while not stop.is_set():
        try:
            tick(settings, clock())
        except Exception:  # noqa: BLE001 - keep the loop alive
            log.exception("tick failed")
        stop.wait(tick_seconds)
    log.info("worker stopped")


def boot_reseed_if_empty(settings: Settings) -> bool:
    """On an empty demo DB run the reset now and mark its jobs done so tick won't repeat them."""
    if settings.instance != "demo":
        return False
    try:
        with closing(connect(settings.db_path)) as conn:
            init_db(conn)
            if conn.execute("SELECT 1 FROM accounts LIMIT 1").fetchone():
                return False
        now = datetime.now(UTC)
        reset(settings, local_today(settings.tz, now), now=now)
        with closing(connect(settings.db_path)) as conn:
            for name in RESEED_JOBS:
                conn.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
                             (STATE_PREFIX + name, now.isoformat()))
            conn.commit()
        return True
    except Exception:  # noqa: BLE001 - a failed reseed must not stop the scheduler
        log.exception("boot reseed failed")
        return False


def main() -> None:
    """Tick forever; SIGINT/SIGTERM exit cleanly."""
    setup_logging()
    settings = Settings.from_env()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    run_loop(settings, stop)


if __name__ == "__main__":
    main()
