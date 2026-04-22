"""statcast_incremental: exercises the 7-day re-pull window."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from src.ingestion.statcast_incremental import _window_bounds, run_incremental_statcast


def test_window_is_seven_days_ending_today() -> None:
    today = date(2026, 4, 22)
    start, end = _window_bounds(today)
    assert end == today
    assert (end - start) == timedelta(days=6)  # inclusive 7-day window


def test_window_bounds_uses_today_by_default() -> None:
    start, end = _window_bounds()
    assert end >= date.today() - timedelta(days=1)  # tolerate cross-midnight
    assert (end - start) == timedelta(days=6)


def test_run_incremental_delegates_to_backfill(monkeypatch: pytest.MonkeyPatch) -> None:
    """Smoke test: verify the entry point is wired correctly."""
    from src.ingestion.statcast_backfill import BackfillReport

    captured = {}

    def fake_backfill(start, end, *, resume=False, engine=None, day_sleep=0.5):
        captured["start"] = start
        captured["end"] = end
        captured["resume"] = resume
        return BackfillReport(start_date=start, end_date=end, days_processed=7, total_pitches=2500)

    monkeypatch.setattr("src.ingestion.statcast_incremental.backfill_statcast", fake_backfill)
    report = run_incremental_statcast()
    assert captured["resume"] is False  # incremental pulls the full window every run
    assert (captured["end"] - captured["start"]).days == 6
    assert report.total_pitches == 2500
