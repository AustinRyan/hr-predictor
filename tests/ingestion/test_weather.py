"""Open-Meteo weather ingestion tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import requests
import vcr
from sqlalchemy import text
from sqlalchemy.engine import Engine
from src.ingestion import weather as weather_mod
from src.ingestion.weather import (
    _celsius_to_f,
    _kmh_to_mph,
    _pick_hour_nearest,
    fetch_archive_range,
    fetch_weather_forecast,
    persist_weather_archive_for_park,
    persist_weather_for_today,
)


@pytest.fixture(autouse=True)
def _plain_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass requests-cache under VCR (they are incompatible: VCR's
    VCRHTTPResponse lacks ``_request_url`` which requests-cache accesses
    when persisting). A plain Session sidesteps this without losing
    test fidelity -- the cache is a prod-runtime concern, not a test one.
    """
    monkeypatch.setattr(weather_mod, "_session", None, raising=False)
    monkeypatch.setattr(weather_mod, "_get_session", lambda: requests.Session())


CASSETTES = Path(__file__).parent / "cassettes"


_vcr = vcr.VCR(
    cassette_library_dir=str(CASSETTES),
    record_mode="new_episodes",
    match_on=["method", "scheme", "host", "port", "path", "query"],
    filter_headers=["user-agent"],
)


def test_unit_conversion_helpers() -> None:
    assert _celsius_to_f(0) == pytest.approx(32.0, rel=1e-3)
    assert _celsius_to_f(100) == pytest.approx(212.0, rel=1e-3)
    assert _kmh_to_mph(0) == pytest.approx(0.0)
    # Canonical: 100 km/h = 62.1371 mph
    assert _kmh_to_mph(100) == pytest.approx(62.137, rel=1e-3)


def test_pick_hour_nearest_picks_closest_index() -> None:
    times = [
        "2026-04-22T22:00",
        "2026-04-22T23:00",
        "2026-04-23T00:00",
        "2026-04-23T01:00",
    ]
    target = datetime(2026, 4, 22, 23, 20, tzinfo=UTC)
    assert _pick_hour_nearest(times, target) == 1  # 23:00 is closest


def test_fetch_weather_returns_converted_units() -> None:
    with _vcr.use_cassette("openmeteo_coors_2024-07-15.yaml"):
        forecast = fetch_weather_forecast(
            park_id=19,  # Coors
            latitude=39.7559,
            longitude=-104.9942,
            forecast_for_utc=datetime(2024, 7, 15, 20, 10, tzinfo=UTC),
        )
    # Coors in mid-July should clear 40F on the low end, below 115F on the high.
    assert 40.0 < forecast["temperature_f"] < 115.0
    assert 0.0 <= forecast["wind_speed_mph"] <= 60.0
    assert 0.0 <= forecast["wind_direction_deg"] <= 360.0
    assert 0.0 <= forecast["humidity_pct"] <= 100.0


@pytest.mark.integration
def test_persist_weather_skips_dome_parks(seeded_parks_teams: Engine) -> None:
    """Dome parks (Tropicana = park_id 12) produce zero weather rows."""
    with seeded_parks_teams.begin() as c:
        c.execute(
            text(
                "UPDATE parks SET roof_type = 'dome', latitude = 27.77, longitude = -82.65 "
                "WHERE park_id = 12"
            )
        )
        c.execute(text("""
                INSERT INTO daily_schedule
                  (game_pk, game_date, home_team_id, away_team_id, venue_id,
                   game_start_utc, status, fetched_at)
                VALUES (999001, CURRENT_DATE, 139, 147, 12, NOW(), 'Scheduled', NOW())
                """))

    # No cassette should be needed -- the dome is filtered before any HTTP call.
    # If the implementation regresses and hits Open-Meteo, VCR will raise because
    # no cassette matches.
    with _vcr.use_cassette("openmeteo_no_calls_expected.yaml"):
        written = persist_weather_for_today(engine=seeded_parks_teams)

    assert written == 0
    with seeded_parks_teams.connect() as c:
        count = c.execute(
            text("SELECT COUNT(*) FROM weather_forecasts WHERE park_id = 12")
        ).scalar_one()
    assert count == 0

    # Cleanup for subsequent tests in the same session.
    with seeded_parks_teams.begin() as c:
        c.execute(text("DELETE FROM daily_schedule WHERE game_pk = 999001"))


@pytest.mark.integration
def test_persist_weather_writes_outdoor_park_rows(seeded_parks_teams: Engine) -> None:
    """A non-dome park with coordinates -> one weather_forecasts row."""
    with seeded_parks_teams.begin() as c:
        c.execute(
            text(
                "UPDATE parks SET roof_type = 'open', latitude = 39.7559, longitude = -104.9942 "
                "WHERE park_id = 19"
            )
        )
        c.execute(text("""
                INSERT INTO daily_schedule
                  (game_pk, game_date, home_team_id, away_team_id, venue_id,
                   game_start_utc, status, fetched_at)
                VALUES (999101, CURRENT_DATE, 115, 147, 19, NOW(), 'Scheduled', NOW())
                """))

    with _vcr.use_cassette("openmeteo_coors_2024-07-15.yaml"):
        written = persist_weather_for_today(engine=seeded_parks_teams)

    assert written == 1
    with seeded_parks_teams.connect() as c:
        row = c.execute(
            text(
                "SELECT temperature_f, wind_speed_mph, humidity_pct "
                "FROM weather_forecasts WHERE park_id = 19"
            )
        ).one()
    # Ranges (not exact values -- the cassette may be recorded for a non-canonical hour).
    assert row.temperature_f is not None
    assert row.wind_speed_mph is not None
    assert 0.0 <= row.humidity_pct <= 100.0

    # Cleanup.
    with seeded_parks_teams.begin() as c:
        c.execute(text("DELETE FROM weather_forecasts WHERE park_id = 19"))
        c.execute(text("DELETE FROM daily_schedule WHERE game_pk = 999101"))


# ---------------------------------------------------------------------------
# Archive (historical) tests
# ---------------------------------------------------------------------------


def test_fetch_archive_range_returns_converted_rows() -> None:
    """Cassette-backed: Coors 2024-07-15 full day, 24 hourly rows in US units."""
    with _vcr.use_cassette("openmeteo_archive_coors_2024-07-15.yaml"):
        rows = fetch_archive_range(
            park_id=19,
            latitude=39.7559,
            longitude=-104.9942,
            start_date=date(2024, 7, 15),
            end_date=date(2024, 7, 15),
        )

    assert len(rows) == 24  # one row per hour for one day
    first = rows[0]
    # Schema check.
    for key in (
        "park_id",
        "valid_hour_utc",
        "temperature_f",
        "feels_like_f",
        "humidity_pct",
        "pressure_hpa",
        "wind_speed_mph",
        "wind_direction_deg",
        "precipitation_mm",
        "cloud_cover_pct",
    ):
        assert key in first, f"missing key {key}"
    # Converted units in plausible ranges for Denver mid-July.
    assert first["park_id"] == 19
    assert first["valid_hour_utc"].tzinfo is not None
    temps = [r["temperature_f"] for r in rows]
    assert all(40.0 < t < 115.0 for t in temps), temps
    assert all(0 <= r["humidity_pct"] <= 100 for r in rows)
    assert all(0 <= r["wind_direction_deg"] <= 360 for r in rows)


@pytest.mark.integration
def test_persist_weather_archive_for_park_writes_rows(
    seeded_parks_teams: Engine,
) -> None:
    """One park, one day -> 24 weather_archive rows, idempotent on re-run."""
    with seeded_parks_teams.begin() as c:
        c.execute(
            text("UPDATE parks SET latitude = 39.7559, longitude = -104.9942 " "WHERE park_id = 19")
        )

    with _vcr.use_cassette("openmeteo_archive_coors_2024-07-15.yaml"):
        written = persist_weather_archive_for_park(
            park_id=19,
            start_date=date(2024, 7, 15),
            end_date=date(2024, 7, 15),
            engine=seeded_parks_teams,
        )
    assert written == 24

    with seeded_parks_teams.connect() as c:
        count = c.execute(
            text("SELECT COUNT(*) FROM weather_archive WHERE park_id = 19")
        ).scalar_one()
        sample = c.execute(
            text(
                "SELECT temperature_f, humidity_pct, wind_speed_mph "
                "FROM weather_archive WHERE park_id = 19 "
                "AND valid_hour_utc = '2024-07-15 20:00+00' LIMIT 1"
            )
        ).one()
    assert count == 24
    # 20:00 UTC = 14:00 MDT Denver peak: ~95F, sub-20% humidity.
    assert 80.0 < sample.temperature_f < 110.0
    assert 0.0 <= sample.humidity_pct <= 50.0

    # Rerun: idempotent (upsert).
    with _vcr.use_cassette("openmeteo_archive_coors_2024-07-15.yaml"):
        again = persist_weather_archive_for_park(
            park_id=19,
            start_date=date(2024, 7, 15),
            end_date=date(2024, 7, 15),
            engine=seeded_parks_teams,
        )
    assert again == 24
    with seeded_parks_teams.connect() as c:
        count2 = c.execute(
            text("SELECT COUNT(*) FROM weather_archive WHERE park_id = 19")
        ).scalar_one()
    assert count2 == 24  # no duplicates

    # Cleanup.
    with seeded_parks_teams.begin() as c:
        c.execute(text("DELETE FROM weather_archive WHERE park_id = 19"))
