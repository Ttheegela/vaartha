"""Job table and due-time logic. Pure: no I/O."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Job:
    """A scheduled job: either every interval, or daily at a local wall-clock time."""

    name: str
    every: timedelta | None = None
    at: time | None = None
    demo_only: bool = False


JOBS = (
    Job("sync", every=timedelta(hours=6)),
    Job("news", every=timedelta(minutes=15)),
    Job("alerts", every=timedelta(hours=1)),
    Job("briefing", at=time(7, 0)),
    Job("backup", at=time(2, 30)),
    Job("demo_reset", at=time(3, 0), demo_only=True),
)


def due(job: Job, now: datetime, last_run: datetime | None, tz: ZoneInfo) -> bool:
    """True if `job` should run now. Datetimes are tz-aware; a long outage yields one run."""
    if job.every is not None:
        return last_run is None or now - last_run >= job.every
    scheduled = datetime.combine(now.astimezone(tz).date(), job.at, tzinfo=tz)
    return now >= scheduled and (last_run is None or last_run < scheduled)
