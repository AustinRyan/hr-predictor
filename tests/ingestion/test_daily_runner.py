"""Daily runner orchestration tests.

Exercises the step-order + error-handling contract with monkeypatched
stubs. Integration-level correctness of each underlying step is covered
by its own module tests.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from src.ingestion import daily_runner as dr
from src.ingestion.daily_runner import DailyRunReport, run_daily


def _stub_all(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    calls: dict[str, MagicMock] = {}
    for name, retval in {
        "refresh_park_factors": 60,
        "persist_daily_schedule": 15,
        "persist_weather_for_today": 12,
        "run_incremental_statcast": None,
    }.items():
        m = MagicMock(return_value=retval)
        monkeypatch.setattr(dr, name, m)
        calls[name] = m

    # run_incremental_statcast needs to return a report-shaped object.
    report_stub = MagicMock()
    report_stub.total_pitches = 3000
    report_stub.days_processed = 7
    calls["run_incremental_statcast"].return_value = report_stub
    return calls


def test_run_daily_calls_all_steps_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(dr, "_park_factors_stale", lambda *_args, **_kw: True)

    report = run_daily(target_date=date(2026, 4, 22))

    calls["refresh_park_factors"].assert_called_once()
    calls["persist_daily_schedule"].assert_called_once_with(date(2026, 4, 22), engine=None)
    calls["persist_weather_for_today"].assert_called_once_with(
        target_date=date(2026, 4, 22), engine=None
    )
    calls["run_incremental_statcast"].assert_called_once()
    assert report.games == 15
    assert report.weather_rows == 12
    assert report.statcast_pitches == 3000
    assert report.failures == []


def test_skip_statcast_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(dr, "_park_factors_stale", lambda *_args, **_kw: False)

    run_daily(target_date=date(2026, 4, 22), skip_statcast=True)

    calls["run_incremental_statcast"].assert_not_called()
    calls["refresh_park_factors"].assert_not_called()  # not stale


def test_skip_weather_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(dr, "_park_factors_stale", lambda *_args, **_kw: False)

    run_daily(target_date=date(2026, 4, 22), skip_weather=True)

    calls["persist_weather_for_today"].assert_not_called()


def test_run_daily_collects_failures_without_bailing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(dr, "_park_factors_stale", lambda *_args, **_kw: False)
    calls["persist_weather_for_today"].side_effect = RuntimeError("openmeteo down")

    report = run_daily(target_date=date(2026, 4, 22))

    # Weather failed but statcast step still ran.
    calls["run_incremental_statcast"].assert_called_once()
    assert any("weather" in f.lower() for f in report.failures)


def test_exit_code_nonzero_on_any_failure() -> None:
    report = DailyRunReport(target_date=date(2026, 4, 22), failures=["weather: boom"])
    assert report.exit_code() == 1

    good = DailyRunReport(target_date=date(2026, 4, 22))
    assert good.exit_code() == 0


def test_park_factors_and_statcast_failures_collected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(dr, "_park_factors_stale", lambda *_args, **_kw: True)
    calls["refresh_park_factors"].side_effect = RuntimeError("savant down")
    calls["persist_daily_schedule"].side_effect = RuntimeError("mlb down")
    calls["run_incremental_statcast"].side_effect = RuntimeError("savant down again")

    report = run_daily(target_date=date(2026, 4, 22))

    # All steps still attempted despite failures.
    calls["persist_weather_for_today"].assert_called_once_with(
        target_date=date(2026, 4, 22), engine=None
    )
    assert any("park_factors" in f for f in report.failures)
    assert any("schedule" in f for f in report.failures)
    assert any("statcast" in f for f in report.failures)
    assert report.exit_code() == 1


def test_parse_date_helper() -> None:
    assert dr._parse_date("2026-04-22") == date(2026, 4, 22)
