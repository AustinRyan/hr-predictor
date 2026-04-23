"""Integration tests for the historical `wx_*` backfill on matchup_features.

The backfill itself lives in `src.ingestion.weather.backfill_wx_for_historical`;
the concern here is that after it runs, a seeded matchup_features row
ends up with physically correct wx_* values joining through games ->
parks -> weather_archive.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.features.weather_physics import air_density_relative
from src.ingestion.weather import backfill_wx_for_historical


@pytest.mark.integration
def test_backfill_populates_wx_for_open_air_park(test_engine: Engine, clean_tables) -> None:
    """Seeded weather_archive hour -> matchup_features.wx_* populated."""
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    game_start = datetime(2024, 7, 15, 20, 0, tzinfo=UTC)  # exact top of hour

    with session_factory() as s:
        # Open-air park with orientation (Coors-like, orientation=0 / north).
        s.execute(
            text(
                "INSERT INTO parks (park_id, name, latitude, longitude, "
                " orientation_deg, roof_type) "
                "VALUES (77701, 'TestOpen', 39.76, -105.0, 0.0, 'open')"
            )
        )
        # Game at exactly 2024-07-15 20:00 UTC.
        s.execute(
            text(
                "INSERT INTO games (game_pk, game_date, season, venue_id, "
                " home_team_id, away_team_id, status, game_start_utc, day_night) "
                "VALUES (777001, '2024-07-15', 2024, 77701, 1, 2, 'Final', "
                " :start, 'D')"
            ),
            {"start": game_start},
        )
        # One historical matchup row (empty wx_*).
        s.execute(
            text(
                "INSERT INTO matchup_features "
                "(game_date, game_pk, batter_id, pitcher_id, is_historical) "
                "VALUES ('2024-07-15', 777001, 77702, 77703, TRUE)"
            )
        )
        # Exact-hour weather_archive row.
        s.execute(
            text(
                "INSERT INTO weather_archive "
                "(park_id, valid_hour_utc, temperature_f, humidity_pct, "
                " pressure_hpa, wind_speed_mph, wind_direction_deg, "
                " precipitation_mm, cloud_cover_pct) "
                "VALUES (77701, :h, 94.0, 15.0, 850.0, 8.0, 180.0, 0.0, 10.0)"
            ),
            {"h": game_start},
        )
        s.commit()

    touched = backfill_wx_for_historical(date(2024, 7, 15), date(2024, 7, 15), engine=test_engine)
    assert touched == 1

    with session_factory() as s:
        row = (
            s.execute(
                text(
                    "SELECT wx_temperature_f, wx_humidity_pct, wx_pressure_hpa, "
                    "wx_wind_speed_mph, wx_air_density_relative, "
                    "wx_wind_carry_lf, wx_wind_carry_cf, wx_wind_carry_rf, "
                    "wx_is_roof_closed "
                    "FROM matchup_features WHERE game_pk = 777001 LIMIT 1"
                )
            )
            .mappings()
            .one()
        )

    assert row["wx_temperature_f"] == pytest.approx(94.0)
    assert row["wx_humidity_pct"] == pytest.approx(15.0)
    assert row["wx_pressure_hpa"] == pytest.approx(850.0)
    assert row["wx_wind_speed_mph"] == pytest.approx(8.0)
    assert row["wx_is_roof_closed"] is False
    # Note: wind_direction_deg is consumed by wind_carry_components but not
    # stored as a separate `wx_wind_direction_deg` column in matchup_features
    # (that column doesn't exist in the schema; only the carry components do).
    # Computed physics: thin Denver air in summer -> density < 1.
    expected_density = air_density_relative(94.0, 15.0, 850.0)
    assert row["wx_air_density_relative"] == pytest.approx(expected_density, rel=1e-6)
    assert expected_density < 1.0  # thinner than sea-level baseline
    # Wind carry components exist (not all zero for a non-zero wind).
    carries = [row["wx_wind_carry_lf"], row["wx_wind_carry_cf"], row["wx_wind_carry_rf"]]
    assert any(abs(c) > 0.01 for c in carries)


@pytest.mark.integration
def test_backfill_dome_park_applies_roof_gating(test_engine: Engine, clean_tables) -> None:
    """Dome parks collapse to climate-neutral baselines regardless of archive row."""
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    game_start = datetime(2024, 7, 15, 23, 0, tzinfo=UTC)

    with session_factory() as s:
        s.execute(
            text(
                "INSERT INTO parks (park_id, name, latitude, longitude, "
                " orientation_deg, roof_type) "
                "VALUES (77801, 'TestDome', 27.77, -82.65, 359.0, 'dome')"
            )
        )
        s.execute(
            text(
                "INSERT INTO games (game_pk, game_date, season, venue_id, "
                " home_team_id, away_team_id, status, game_start_utc, day_night) "
                "VALUES (777801, '2024-07-15', 2024, 77801, 1, 2, 'Final', "
                " :start, 'N')"
            ),
            {"start": game_start},
        )
        s.execute(
            text(
                "INSERT INTO matchup_features "
                "(game_date, game_pk, batter_id, pitcher_id, is_historical) "
                "VALUES ('2024-07-15', 777801, 77802, 77803, TRUE)"
            )
        )
        s.execute(
            text(
                "INSERT INTO weather_archive "
                "(park_id, valid_hour_utc, temperature_f, humidity_pct, "
                " pressure_hpa, wind_speed_mph, wind_direction_deg, "
                " precipitation_mm, cloud_cover_pct) "
                "VALUES (77801, :h, 88.0, 80.0, 1015.0, 12.0, 200.0, 0.0, 30.0)"
            ),
            {"h": game_start},
        )
        s.commit()

    backfill_wx_for_historical(date(2024, 7, 15), date(2024, 7, 15), engine=test_engine)

    with session_factory() as s:
        row = (
            s.execute(
                text(
                    "SELECT wx_temperature_f, wx_humidity_pct, wx_wind_speed_mph, "
                    "wx_air_density_relative, wx_is_roof_closed "
                    "FROM matchup_features WHERE game_pk = 777801 LIMIT 1"
                )
            )
            .mappings()
            .one()
        )
    # Climate-neutral baselines from apply_roof_gating.
    assert row["wx_is_roof_closed"] is True
    assert row["wx_temperature_f"] == pytest.approx(72.0)
    assert row["wx_humidity_pct"] == pytest.approx(50.0)
    assert row["wx_wind_speed_mph"] == pytest.approx(0.0)
    assert row["wx_air_density_relative"] == pytest.approx(1.0)
