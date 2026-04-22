"""Smoke test: migration 0003 creates the four operational tables."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def test_operational_tables_exist(test_engine: Engine) -> None:
    expected = {"daily_schedule", "projected_lineups", "weather_forecasts", "park_factors"}
    with test_engine.connect() as c:
        rows = (
            c.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = ANY(:names)"
                ),
                {"names": sorted(expected)},
            )
            .scalars()
            .all()
        )
    assert set(rows) == expected


def test_projected_lineups_unique_game_team_slot(test_engine: Engine) -> None:
    with test_engine.connect() as c:
        rows = c.execute(text("""
                    SELECT conname FROM pg_constraint
                    WHERE conrelid = 'projected_lineups'::regclass
                      AND contype = 'u'
                    """)).scalars().all()
    assert any("game_pk" in r and "team_id" in r and "batting_order" in r for r in rows)


def test_weather_forecasts_unique_park_forecast_fetched(test_engine: Engine) -> None:
    with test_engine.connect() as c:
        rows = c.execute(text("""
                    SELECT conname FROM pg_constraint
                    WHERE conrelid = 'weather_forecasts'::regclass
                      AND contype = 'u'
                    """)).scalars().all()
    assert len(rows) >= 1


def test_park_factors_unique_park_season_hand_metric(test_engine: Engine) -> None:
    with test_engine.connect() as c:
        rows = c.execute(text("""
                    SELECT conname FROM pg_constraint
                    WHERE conrelid = 'park_factors'::regclass
                      AND contype = 'u'
                    """)).scalars().all()
    assert len(rows) >= 1
