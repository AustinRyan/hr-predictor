"""Daily ingestion CLI orchestrator.

Step order:
  1. Refresh park factors if stale (>7d since last update)
  2. Fetch today's schedule + probable pitchers + projected lineups
  3. Fetch weather for each non-dome game's park
  4. Pull incremental Statcast (last 7 days)

Failure handling: every step runs even if earlier ones fail; failures
are collected into the report; exit code is non-zero if any step raised.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from src.core.db import get_engine
from src.core.logging_config import configure_logging
from src.core.models import ParkFactor
from src.core.time import current_mlb_date
from src.ingestion.mlb_statsapi import persist_daily_schedule
from src.ingestion.park_factors import refresh_park_factors
from src.ingestion.statcast_incremental import run_incremental_statcast
from src.ingestion.weather import persist_weather_for_today

_log = logging.getLogger(__name__)

PARK_FACTORS_STALE_DAYS = 7


@dataclass(slots=True)
class DailyRunReport:
    target_date: date
    park_factors_refreshed: int = 0
    games: int = 0
    weather_rows: int = 0
    statcast_pitches: int = 0
    statcast_days: int = 0
    failures: list[str] = field(default_factory=list)

    def exit_code(self) -> int:
        return 1 if self.failures else 0


def _park_factors_stale(engine: Engine, today: date) -> bool:
    session_factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        latest = s.execute(
            select(ParkFactor.updated_at).order_by(ParkFactor.updated_at.desc()).limit(1)
        ).scalar_one_or_none()
    if latest is None:
        return True
    return (datetime.now(UTC) - latest) > timedelta(days=PARK_FACTORS_STALE_DAYS)


def run_daily(
    *,
    target_date: date | None = None,
    skip_statcast: bool = False,
    skip_weather: bool = False,
    engine: Engine | None = None,
) -> DailyRunReport:
    target_date = target_date or current_mlb_date()
    report = DailyRunReport(target_date=target_date)

    # Step 1: park factors.
    try:
        stale_engine = engine or get_engine()
        if _park_factors_stale(stale_engine, target_date):
            report.park_factors_refreshed = refresh_park_factors(target_date.year, engine=engine)
        else:
            _log.info("park factors fresh, skipping refresh")
    except Exception as exc:  # noqa: BLE001
        report.failures.append(f"park_factors: {exc!r}")
        _log.exception("park_factors step failed")

    # Step 2: schedule + lineups (lineups pulled inside persist_daily_schedule).
    try:
        report.games = persist_daily_schedule(target_date, engine=engine)
    except Exception as exc:  # noqa: BLE001
        report.failures.append(f"schedule: {exc!r}")
        _log.exception("schedule step failed")

    # Step 3: weather.
    if not skip_weather:
        try:
            report.weather_rows = persist_weather_for_today(target_date=target_date, engine=engine)
        except Exception as exc:  # noqa: BLE001
            report.failures.append(f"weather: {exc!r}")
            _log.exception("weather step failed")

    # Step 4: incremental statcast.
    if not skip_statcast:
        try:
            sc = run_incremental_statcast(engine=engine)
            report.statcast_pitches = sc.total_pitches
            report.statcast_days = sc.days_processed
        except Exception as exc:  # noqa: BLE001
            report.failures.append(f"statcast: {exc!r}")
            _log.exception("statcast step failed")

    _log.info(
        "daily run summary",
        extra={
            "date": target_date.isoformat(),
            "games": report.games,
            "weather_rows": report.weather_rows,
            "statcast_pitches": report.statcast_pitches,
            "failures": report.failures,
        },
    )
    return report


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def main() -> int:  # pragma: no cover
    configure_logging()
    parser = argparse.ArgumentParser(description="Daily ingestion runner")
    parser.add_argument("--date", type=_parse_date, default=None)
    parser.add_argument("--skip-statcast", action="store_true")
    parser.add_argument("--skip-weather", action="store_true")
    args = parser.parse_args()

    report = run_daily(
        target_date=args.date,
        skip_statcast=args.skip_statcast,
        skip_weather=args.skip_weather,
    )
    return report.exit_code()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
