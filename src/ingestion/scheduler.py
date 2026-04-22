"""APScheduler foundation for daily + pre-game ingestion runs.

Jobs are registered but not started until `start_scheduler()` is
called explicitly (so unit tests can introspect the trigger config
without a blocking main loop).

Deployment notes (local dev):
    # foreground process — Ctrl-C to stop
    uv run python -m src.ingestion.scheduler

For production, wrap in systemd or launchd. Railway / Render: use their
native cron trigger pointing at `python -m src.ingestion.daily_runner`
for the morning run, and the same with `--skip-statcast` for the hourly
pre-game window.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core.logging_config import configure_logging
from src.ingestion.daily_runner import run_daily

_log = logging.getLogger(__name__)

JOB_MORNING_PULL = "morning_pull"
JOB_PREGAME_REFRESH = "pregame_refresh"

_ET = "America/New_York"


def _morning_job() -> None:  # pragma: no cover - runs inside scheduler
    run_daily()


def _pregame_job() -> None:  # pragma: no cover - runs inside scheduler
    run_daily(skip_statcast=True)


def build_scheduler() -> BlockingScheduler:
    """Return a scheduler with jobs registered but not yet started."""
    sched = BlockingScheduler(timezone=_ET)
    sched.add_job(
        _morning_job,
        trigger=CronTrigger(hour=7, minute=0, timezone=_ET),
        id=JOB_MORNING_PULL,
        name="Morning full ingestion",
        replace_existing=True,
    )
    sched.add_job(
        _pregame_job,
        trigger=CronTrigger(hour="14-22", minute=0, timezone=_ET),
        id=JOB_PREGAME_REFRESH,
        name="Pre-game lineup + weather refresh",
        replace_existing=True,
    )
    return sched


def start_scheduler() -> None:  # pragma: no cover - blocking
    configure_logging()
    sched = build_scheduler()
    _log.info(
        "scheduler starting",
        extra={"jobs": [j.id for j in sched.get_jobs()]},
    )
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown(wait=False)


if __name__ == "__main__":  # pragma: no cover
    start_scheduler()
