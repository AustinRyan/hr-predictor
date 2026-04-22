"""Smoke tests for the Phase 3 matchup_features migration."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine


def test_matchup_features_table_exists(test_engine: Engine) -> None:
    with test_engine.connect() as c:
        row = c.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'matchup_features'"
            )
        ).scalar_one()
    assert row == 1


def test_matchup_features_pk_includes_game_date(test_engine: Engine) -> None:
    """Postgres requires the partition key in the PK — game_date must be present."""
    with test_engine.connect() as c:
        rows = c.execute(text("""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a
                  ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = 'matchup_features'::regclass
                  AND i.indisprimary
                ORDER BY array_position(i.indkey, a.attnum)
                """)).scalars().all()
    assert list(rows) == ["game_date", "game_pk", "batter_id", "pitcher_id"]


def test_matchup_features_yearly_partitions_exist(test_engine: Engine) -> None:
    start_year = 2021
    end_year = date.today().year + 1
    with test_engine.connect() as c:
        rows = (
            c.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename LIKE 'matchup_features_%'"
                )
            )
            .scalars()
            .all()
        )
    present = set(rows)
    for y in range(start_year, end_year + 1):
        assert f"matchup_features_{y}" in present, f"missing partition for {y}"


def test_matchup_features_indexes_present(test_engine: Engine) -> None:
    expected = {
        "idx_matchup_features_batter_date",
        "idx_matchup_features_pitcher_date",
        "idx_matchup_features_game_pk",
        "idx_matchup_features_historical",
    }
    with test_engine.connect() as c:
        rows = (
            c.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = 'matchup_features' "
                    "AND indexname = ANY(:names)"
                ),
                {"names": sorted(expected)},
            )
            .scalars()
            .all()
        )
    assert set(rows) == expected
