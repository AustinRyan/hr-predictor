"""Daily incremental Statcast: re-pulls the last 7 days.

Savant backfills reviewed plays for ~3–5 days after a game. Re-pulling
the last 7 days each run is cheap (pybaseball's day-level cache handles
the stable days, and the upsert ON CONFLICT handles the rewrites). This
keeps our local copy in sync with Savant corrections without the
operator having to think about it.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.engine import Engine

from src.ingestion.statcast_backfill import BackfillReport, backfill_statcast

_log = logging.getLogger(__name__)

WINDOW_DAYS = 7


def _window_bounds(today: date | None = None) -> tuple[date, date]:
    end = today or date.today()
    start = end - timedelta(days=WINDOW_DAYS - 1)
    return start, end


def run_incremental_statcast(
    today: date | None = None,
    *,
    engine: Engine | None = None,
) -> BackfillReport:
    """Re-pull the trailing 7-day window. Bypasses resume state (full re-pull)."""
    start, end = _window_bounds(today)
    _log.info(
        "incremental statcast window",
        extra={"start": start.isoformat(), "end": end.isoformat()},
    )
    report = backfill_statcast(start, end, resume=False, engine=engine, day_sleep=0.5)
    _log.info(
        "incremental statcast complete",
        extra={
            "days": report.days_processed,
            "pitches": report.total_pitches,
            "games": report.total_games,
        },
    )
    return report
