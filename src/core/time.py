"""Project date/time helpers."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

MLB_TIMEZONE = ZoneInfo("America/New_York")


def current_mlb_date(now: datetime | None = None) -> date:
    """Return the current MLB slate date using Eastern time."""
    instant = now or datetime.now(MLB_TIMEZONE)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=MLB_TIMEZONE)
    return instant.astimezone(MLB_TIMEZONE).date()
