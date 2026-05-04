"""Smoke tests for the odds_snapshots migration."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.core.models import OddsSnapshot


def test_odds_snapshots_table_exists(test_engine: Engine) -> None:
    with test_engine.connect() as c:
        tables = c.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'odds_snapshots'"
            )
        ).scalars()
    assert list(tables) == ["odds_snapshots"]


def test_odds_snapshots_columns_present(test_engine: Engine) -> None:
    expected = {
        "id",
        "snapshot_key",
        "provider",
        "sport_key",
        "event_id",
        "game_pk",
        "game_date",
        "commence_time",
        "home_team",
        "away_team",
        "bookmaker_key",
        "bookmaker_title",
        "market_key",
        "outcome_name",
        "player_name",
        "batter_id",
        "price_american",
        "point",
        "implied_probability",
        "no_vig_probability",
        "market_last_update",
        "fetched_at",
        "raw_outcome",
    }
    with test_engine.connect() as c:
        cols = set(
            c.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'odds_snapshots' AND table_schema = 'public'"
                )
            ).scalars()
        )
    assert expected <= cols


def test_odds_snapshots_unique_snapshot_key(test_engine: Engine) -> None:
    with test_engine.connect() as c:
        constraints = set(
            c.execute(
                text(
                    "SELECT con.conname "
                    "FROM pg_constraint con "
                    "WHERE con.conrelid = 'odds_snapshots'::regclass AND con.contype = 'u'"
                )
            ).scalars()
        )
    assert "uq_odds_snapshots_snapshot_key" in constraints


def test_odds_snapshots_indexes_present(test_engine: Engine) -> None:
    expected = {
        "ix_odds_snapshots_game_batter_market_fetched",
        "ix_odds_snapshots_batter_date",
    }
    with test_engine.connect() as c:
        indexes = set(
            c.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = 'odds_snapshots'"
                )
            ).scalars()
        )
    assert expected <= indexes


def test_odds_snapshots_upsert_by_snapshot_key(test_engine: Engine) -> None:
    row = {
        "snapshot_key": "abc123",
        "provider": "prop_line",
        "sport_key": "baseball_mlb",
        "event_id": "evt1",
        "game_pk": 999001,
        "game_date": date(2026, 5, 1),
        "commence_time": datetime(2026, 5, 1, 23, 5, tzinfo=UTC),
        "home_team": "New York Yankees",
        "away_team": "Boston Red Sox",
        "bookmaker_key": "draftkings",
        "bookmaker_title": "DraftKings",
        "market_key": "batter_home_runs",
        "outcome_name": "Over",
        "player_name": "Aaron Judge",
        "batter_id": 592450,
        "price_american": 650,
        "point": 0.5,
        "implied_probability": 100 / 750,
        "no_vig_probability": 0.12,
        "market_last_update": datetime(2026, 5, 1, 16, 0, tzinfo=UTC),
        "fetched_at": datetime(2026, 5, 1, 16, 1, tzinfo=UTC),
        "raw_outcome": {"name": "Over", "description": "Aaron Judge", "price": 650},
    }
    with test_engine.begin() as c:
        stmt = pg_insert(OddsSnapshot).values(row)
        c.execute(
            stmt.on_conflict_do_update(
                constraint="uq_odds_snapshots_snapshot_key",
                set_={"price_american": stmt.excluded.price_american},
            )
        )
        c.execute(
            stmt.on_conflict_do_update(
                constraint="uq_odds_snapshots_snapshot_key",
                set_={"price_american": stmt.excluded.price_american},
            )
        )
        count = c.execute(text("SELECT COUNT(*) FROM odds_snapshots")).scalar_one()
    assert count == 1
