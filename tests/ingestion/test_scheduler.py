"""Scheduler wiring tests. No actual long-running scheduler is started."""

from __future__ import annotations

from src.ingestion.scheduler import JOB_MORNING_PULL, JOB_PREGAME_REFRESH, build_scheduler


def test_build_scheduler_registers_expected_jobs() -> None:
    sched = build_scheduler()
    job_ids = {j.id for j in sched.get_jobs()}
    assert JOB_MORNING_PULL in job_ids
    assert JOB_PREGAME_REFRESH in job_ids


def test_morning_pull_is_daily_at_7am_et() -> None:
    sched = build_scheduler()
    job = sched.get_job(JOB_MORNING_PULL)
    trigger = str(job.trigger)
    assert "hour='7'" in trigger
    assert "minute='0'" in trigger


def test_pregame_refresh_is_hourly_2pm_10pm_et() -> None:
    sched = build_scheduler()
    job = sched.get_job(JOB_PREGAME_REFRESH)
    trigger = str(job.trigger)
    assert "hour='14-22'" in trigger
    assert "minute='0'" in trigger
