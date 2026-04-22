"""Bullpen feature SQL tests (league-wide proxy)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.features.bullpen import bullpen_sql


def test_sql_has_expected_columns() -> None:
    sql = bullpen_sql()
    for c in [
        "game_pk",
        "batter_id",
        "pitcher_id",
        "reference_date",
        "bp_barrel_pct_allowed_season",
        "bp_hr_per_9_season",
    ]:
        assert c in sql, f"missing column {c}"


def test_sql_strict_less_than_reference_date() -> None:
    import re

    sql = bullpen_sql()
    assert re.search(r"<=\s*[a-z_.]*reference_date", sql, re.IGNORECASE) is None


def test_sql_excludes_matchup_pitcher() -> None:
    """The proxy MUST filter out the starter of this matchup."""
    sql = bullpen_sql()
    assert "sp.pitcher != mk.pitcher_id" in sql or "sp.pitcher <> mk.pitcher_id" in sql


@pytest.fixture()
def seeded_bullpen(test_engine: Engine, clean_tables) -> Engine:
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text("INSERT INTO parks (park_id, name) VALUES (78101, 'tp') ON CONFLICT DO NOTHING")
        )
        # Pitcher 781001 (the starter in our matchup): 50 PAs, 0 HR, 0 barrels.
        for i in range(50):
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    " launch_speed, launch_speed_angle, events) "
                    "VALUES ('2024-06-01', :gp, 1, 1, 781100, 781001, 90.0, 3, 'single')"
                ),
                {"gp": 7810000 + i},
            )
        # Pitchers 781002 and 781003 (the "league" / bullpen): 100 PAs combined, 10 HR, 15 barrels (of 100 BIP).
        for i in range(50):
            ev = "home_run" if i < 5 else "single"
            lsa = 6 if i < 10 else 3  # first 10 barrels
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    " launch_speed, launch_speed_angle, events) "
                    "VALUES ('2024-06-01', :gp, 1, 1, 781200, 781002, 95.0, :lsa, :ev)"
                ),
                {"gp": 7811000 + i, "lsa": lsa, "ev": ev},
            )
        for i in range(50):
            ev = "home_run" if i < 5 else "single"
            lsa = 6 if i < 5 else 4
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    " launch_speed, launch_speed_angle, events) "
                    "VALUES ('2024-06-01', :gp, 1, 1, 781200, 781003, 95.0, :lsa, :ev)"
                ),
                {"gp": 7812000 + i, "lsa": lsa, "ev": ev},
            )
        s.commit()
    return test_engine


@pytest.mark.integration
def test_bullpen_aggregates_exclude_starter(seeded_bullpen: Engine) -> None:
    sql = f"""
        WITH matchup_keys AS (
            SELECT 1 AS game_pk, 781100 AS batter_id, 781001 AS pitcher_id,
                   DATE '2024-08-01' AS reference_date
        ),
        bp AS ({bullpen_sql()})
        SELECT * FROM bp
    """
    session_factory = sessionmaker(bind=seeded_bullpen, future=True, expire_on_commit=False)
    with session_factory() as s:
        row = s.execute(text(sql)).mappings().one()

    # Excludes 781001's 50 PAs (0 HR, 0 barrels).
    # Includes 781002 + 781003: 100 PAs, 10 HR, 15 barrels / 100 BIP = 0.15.
    assert row["bp_barrel_pct_allowed_season"] == pytest.approx(0.15, abs=0.01)
    # HR/9 ≈ (10 HR / 100 PA) * 38.7 ≈ 3.87
    assert row["bp_hr_per_9_season"] == pytest.approx(3.87, abs=0.3)

    # Sanity: if the starter leaked in, we'd have 10 HR / 150 PA → lower HR/9. Must NOT match that.
    assert row["bp_hr_per_9_season"] != pytest.approx(10 / 150 * 38.7, abs=0.3)
