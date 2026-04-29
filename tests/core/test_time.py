"""Tests for shared date/time helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from src.core.time import current_mlb_date


def test_current_mlb_date_uses_eastern_calendar_day() -> None:
    assert current_mlb_date(datetime(2026, 4, 29, 2, 30, tzinfo=UTC)).isoformat() == "2026-04-28"


def test_current_mlb_date_handles_naive_datetime_as_localish_input() -> None:
    assert current_mlb_date(datetime(2026, 4, 28, 23, 30)).isoformat() == "2026-04-28"
