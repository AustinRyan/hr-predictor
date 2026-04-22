"""Smoke test: migration 0003 creates the four operational tables."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine


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


def _unique_columns(c: Connection, table: str) -> set[str]:
    """Return the column set of the single unique constraint on `table`.

    Asserts there is exactly one UNIQUE constraint; fails loudly otherwise
    so a future accidental addition is caught.
    """
    rows = c.execute(
        text("""
            SELECT c.conname,
                   ARRAY_AGG(a.attname ORDER BY array_position(c.conkey, a.attnum))
            FROM pg_constraint c
            JOIN pg_attribute a
              ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
            WHERE c.conrelid = (:t)::regclass
              AND c.contype = 'u'
            GROUP BY c.conname
            """),
        {"t": table},
    ).all()
    assert len(rows) == 1, f"expected exactly one unique constraint on {table}, got {rows}"
    return set(rows[0][1])


def test_projected_lineups_unique_on_game_team_slot(test_engine: Engine) -> None:
    with test_engine.connect() as c:
        cols = _unique_columns(c, "projected_lineups")
    assert cols == {"game_pk", "team_id", "batting_order"}


def test_weather_forecasts_unique_on_park_forecast_fetched(test_engine: Engine) -> None:
    with test_engine.connect() as c:
        cols = _unique_columns(c, "weather_forecasts")
    assert cols == {"park_id", "forecast_for_utc", "fetched_at"}


def test_park_factors_unique_on_park_season_hand_metric(test_engine: Engine) -> None:
    with test_engine.connect() as c:
        cols = _unique_columns(c, "park_factors")
    assert cols == {"park_id", "season", "batter_handedness", "metric"}


def test_projected_lineups_cascade_delete_on_schedule(test_engine: Engine) -> None:
    """Deleting a daily_schedule row must cascade-delete its projected_lineups."""
    with test_engine.begin() as c:
        # Seed a minimal park for the FK.
        c.execute(
            text(
                "INSERT INTO parks (park_id, name) VALUES (99901, 'test_park') "
                "ON CONFLICT DO NOTHING"
            )
        )
        c.execute(text("""
                INSERT INTO daily_schedule
                  (game_pk, game_date, home_team_id, away_team_id, venue_id,
                   game_start_utc, status)
                VALUES (99990001, CURRENT_DATE, 1, 2, 99901, NOW(), 'Scheduled')
                """))
        c.execute(text("""
                INSERT INTO projected_lineups
                  (game_pk, team_id, batter_id, batting_order)
                VALUES (99990001, 1, 12345, 1)
                """))

    with test_engine.begin() as c:
        c.execute(text("DELETE FROM daily_schedule WHERE game_pk = 99990001"))

    with test_engine.connect() as c:
        leftover = c.execute(
            text("SELECT COUNT(*) FROM projected_lineups WHERE game_pk = 99990001")
        ).scalar_one()
    assert leftover == 0

    # Tidy: remove the synthetic park so it doesn't leak into other tests.
    with test_engine.begin() as c:
        c.execute(text("DELETE FROM parks WHERE park_id = 99901"))
