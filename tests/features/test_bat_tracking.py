"""Tests for batter bat-tracking SQL generator."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.features.batter_tracking import bat_tracking_sql


def test_sql_returns_string_with_expected_columns() -> None:
    sql = bat_tracking_sql()
    for c in [
        "game_pk",
        "batter_id",
        "reference_date",
        "b_avg_bat_speed",
        "b_squared_up_pct",
        "b_blast_rate",
    ]:
        assert c in sql, f"missing column {c}"
    assert "matchup_keys" in sql.lower()


def test_sql_uses_strict_less_than_reference_date() -> None:
    import re

    sql = bat_tracking_sql()
    assert re.search(r"<=\s*[a-z_.]*reference_date", sql, re.IGNORECASE) is None


@pytest.fixture()
def seeded_bat_tracking_data(test_engine: Engine, clean_tables) -> Engine:
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text("INSERT INTO parks (park_id, name) VALUES (77801, 'tp') " "ON CONFLICT DO NOTHING")
        )
        # Batter 778001 with 2024 bat-tracking data, 10 swings:
        #   5 swings with bat_speed=80, launch_speed=72 (ratio 0.9 → squared-up; blast since ≥75)
        #   3 swings with bat_speed=70, launch_speed=55 (ratio 0.79 → NOT squared-up, NOT blast)
        #   2 swings with bat_speed=85, launch_speed=68 (ratio 0.8 → squared-up; blast since ≥75)
        # avg bat_speed = (5*80 + 3*70 + 2*85) / 10 = (400 + 210 + 170) / 10 = 78
        # squared-up: 7 / 10 = 0.7 (ratio >= 0.8 for first and third groups)
        # blast: 7 / 10 = 0.7 (same 7 swings; all have bat_speed >= 75 already)

        # For ratio boundary: 0.79 < 0.8 (exclusive), 0.8 = 0.8 (inclusive)
        pitches = (
            # (bat_speed, launch_speed) × count
            [(80.0, 72.0)] * 5
            + [(70.0, 55.0)] * 3
            + [(85.0, 68.0)] * 2
        )
        base_date = date(2024, 6, 1)
        for i, (bs, ls) in enumerate(pitches):
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    " bat_speed, launch_speed, events) "
                    "VALUES (:gd, :gp, :ab, 1, 778001, 778002, :bs, :ls, 'single')"
                ),
                {"gd": base_date, "gp": 7780000 + i, "ab": 1, "bs": bs, "ls": ls},
            )
        # One pre-2024 swing (should be outside 30d window anyway, but double-safeguard).
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                " bat_speed, launch_speed, events) "
                "VALUES ('2023-09-15', 7780900, 1, 1, 778001, 778002, NULL, 90.0, 'single')"
            )
        )
        s.commit()
    return test_engine


@pytest.mark.integration
def test_bat_tracking_computes_averages(seeded_bat_tracking_data: Engine) -> None:
    sql = f"""
        WITH matchup_keys AS (
            SELECT 1 AS game_pk, 778001 AS batter_id, DATE '2024-06-15' AS reference_date
        ),
        bt AS (
            {bat_tracking_sql()}
        )
        SELECT * FROM bt
    """
    session_factory = sessionmaker(
        bind=seeded_bat_tracking_data, future=True, expire_on_commit=False
    )
    with session_factory() as s:
        row = s.execute(text(sql)).mappings().one()

    # All 10 pitches fall within 30d window of 2024-06-15 (they're on 2024-06-01).
    assert row["b_avg_bat_speed"] == pytest.approx(78.0, abs=0.5)
    assert row["b_squared_up_pct"] == pytest.approx(0.7, abs=0.05)
    assert row["b_blast_rate"] == pytest.approx(0.7, abs=0.05)


@pytest.mark.integration
def test_bat_tracking_null_for_pre_2024_batter(test_engine: Engine, clean_tables) -> None:
    """Batter with only pre-2024 pitches (bat_speed always NULL) → all three NULL."""
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text(
                "INSERT INTO parks (park_id, name) VALUES (77802, 'tp2') " "ON CONFLICT DO NOTHING"
            )
        )
        # 3 pre-2024 pitches, all NULL bat_speed.
        for i in range(3):
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    " bat_speed, launch_speed, events) "
                    "VALUES ('2022-06-01', :gp, 1, 1, 778301, 778302, NULL, 90.0, 'single')"
                ),
                {"gp": 7783000 + i},
            )
        s.commit()

        sql = f"""
            WITH matchup_keys AS (
                SELECT 1 AS game_pk, 778301 AS batter_id, DATE '2022-06-15' AS reference_date
            ),
            bt AS (
                {bat_tracking_sql()}
            )
            SELECT * FROM bt
        """
        row = s.execute(text(sql)).mappings().one()

    assert row["b_avg_bat_speed"] is None
    assert row["b_squared_up_pct"] is None
    assert row["b_blast_rate"] is None


@pytest.mark.integration
def test_bat_tracking_window_is_30d(seeded_bat_tracking_data: Engine) -> None:
    """Reference 2024-08-15: the 10 swings on 2024-06-01 are 75 days old → outside 30d → all NULL."""
    sql = f"""
        WITH matchup_keys AS (
            SELECT 1 AS game_pk, 778001 AS batter_id, DATE '2024-08-15' AS reference_date
        ),
        bt AS (
            {bat_tracking_sql()}
        )
        SELECT * FROM bt
    """
    session_factory = sessionmaker(
        bind=seeded_bat_tracking_data, future=True, expire_on_commit=False
    )
    with session_factory() as s:
        row = s.execute(text(sql)).mappings().one()

    assert row["b_avg_bat_speed"] is None
    assert row["b_squared_up_pct"] is None
    assert row["b_blast_rate"] is None
