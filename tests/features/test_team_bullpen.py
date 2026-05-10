"""Opponent team bullpen feature SQL tests."""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.features.team_bullpen import TEAM_BULLPEN_COLS, team_bullpen_sql


def test_sql_has_expected_columns() -> None:
    sql = team_bullpen_sql()
    for column in (
        "game_pk",
        "batter_id",
        "pitcher_id",
        "reference_date",
        "opp_team_id",
        *TEAM_BULLPEN_COLS,
    ):
        assert column in sql, f"missing column {column}"


def test_sql_uses_strict_reference_date_filters() -> None:
    sql = team_bullpen_sql()
    assert "sp.game_date < tk.reference_date" in sql
    assert re.search(r"<=\s*[a-z_.]*reference_date", sql, re.IGNORECASE) is None


def test_sql_derives_pitcher_team_from_inning_context() -> None:
    sql = team_bullpen_sql()
    assert "WHEN sp.inning_topbot = 'Top' THEN g.home_team_id" in sql
    assert "WHEN sp.inning_topbot = 'Bot' THEN g.away_team_id" in sql


def test_sql_excludes_team_game_starter_from_relief_aggregates() -> None:
    sql = team_bullpen_sql()
    assert re.search(r"pitcher_id\s*(<>|!=)\s*\S*starter_id", sql) is not None


def test_sql_aggregates_once_per_team_date_before_matchup_fanout() -> None:
    sql = team_bullpen_sql()
    assert "team_date_keys AS" in sql
    assert re.search(
        r"GROUP BY\s+tk\.reference_date,\s+tk\.opp_team_id",
        sql,
        re.IGNORECASE,
    )
    assert "JOIN team_date_bp tdb" in sql


@pytest.fixture()
def seeded_team_bullpen(test_engine: Engine, clean_tables) -> Engine:
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(text("INSERT INTO parks (park_id, name) VALUES (99001, 'team bp park')"))
        s.execute(
            text(
                "INSERT INTO games "
                "(game_pk, game_date, season, venue_id, home_team_id, away_team_id, status) "
                "VALUES (990001, '2024-06-01', 2024, 99001, 100, 200, 'Final')"
            )
        )
        s.execute(
            text(
                "INSERT INTO games "
                "(game_pk, game_date, season, venue_id, home_team_id, away_team_id, status) "
                "VALUES (990002, '2024-06-10', 2024, 99001, 100, 200, 'Final')"
            )
        )

        # Home starter: top of the first. This noisy HR must be excluded
        # from home-team relief aggregates.
        for ab in range(1, 4):
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    "inning, inning_topbot, stand, launch_speed, launch_speed_angle, events) "
                    "VALUES ('2024-06-01', 990001, :ab, 1, 1000, 9001, "
                    "1, 'Top', 'L', 110.0, 6, 'home_run')"
                ),
                {"ab": ab},
            )

        # Home reliever: top-half innings mean the home team is pitching.
        home_reliever_rows = [
            (10, "L", 104.0, 6, "home_run"),
            (11, "L", 90.0, 3, "single"),
            (12, "R", 96.0, 3, "single"),
            (13, "R", 82.0, 2, "field_out"),
        ]
        for ab, stand, launch_speed, lsa, event in home_reliever_rows:
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    "inning, inning_topbot, stand, launch_speed, launch_speed_angle, events) "
                    "VALUES ('2024-06-01', 990001, :ab, 1, :batter, 9002, "
                    "6, 'Top', :stand, :launch_speed, :lsa, :event)"
                ),
                {
                    "ab": ab,
                    "batter": 2000 + ab,
                    "stand": stand,
                    "launch_speed": launch_speed,
                    "lsa": lsa,
                    "event": event,
                },
            )

        # Away starter/reliever in bottom-half innings. Included only when
        # opp_team_id = 200.
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                "inning, inning_topbot, stand, launch_speed, launch_speed_angle, events) "
                "VALUES ('2024-06-01', 990001, 20, 1, 3000, 9011, "
                "1, 'Bot', 'R', 105.0, 6, 'home_run')"
            )
        )
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                "inning, inning_topbot, stand, launch_speed, launch_speed_angle, events) "
                "VALUES ('2024-06-01', 990001, 21, 1, 3001, 9012, "
                "6, 'Bot', 'R', 80.0, 2, 'single')"
            )
        )

        # Same-day clobber should be excluded by strict reference_date filter.
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                "inning, inning_topbot, stand, launch_speed, launch_speed_angle, events) "
                "VALUES ('2024-06-10', 990002, 1, 1, 4000, 9002, "
                "7, 'Top', 'L', 115.0, 6, 'home_run')"
            )
        )
        s.commit()
    return test_engine


@pytest.mark.integration
def test_team_bullpen_aggregates_home_reliever_only(seeded_team_bullpen: Engine) -> None:
    sql = f"""
        WITH matchup_keys AS (
            SELECT
                990002 AS game_pk,
                DATE '2024-06-10' AS reference_date,
                4000 AS batter_id,
                9001 AS pitcher_id,
                TRUE AS is_historical,
                100 AS opp_team_id
        ),
        team_bp AS ({team_bullpen_sql()})
        SELECT * FROM team_bp
    """
    session_factory = sessionmaker(bind=seeded_team_bullpen, future=True, expire_on_commit=False)
    with session_factory() as s:
        row = s.execute(text(sql)).mappings().one()

    assert row["opp_team_id"] == 100
    assert row["opp_bp_hr_per_pa_30d"] == pytest.approx(0.25)
    assert row["opp_bp_hr_per_pa_season"] == pytest.approx(0.25)
    assert row["opp_bp_barrel_pct_allowed_30d"] == pytest.approx(0.25)
    assert row["opp_bp_barrel_pct_allowed_season"] == pytest.approx(0.25)
    assert row["opp_bp_hardhit_pct_allowed_30d"] == pytest.approx(0.5)
    assert row["opp_bp_hardhit_pct_allowed_season"] == pytest.approx(0.5)
    assert row["opp_bp_lhb_hr_per_pa_season"] == pytest.approx(0.5)
    assert row["opp_bp_rhb_hr_per_pa_season"] == pytest.approx(0.0)
    assert row["opp_bp_pitches_last_3d"] == 0


@pytest.mark.integration
def test_team_bullpen_aggregates_away_reliever_from_bottom_half(
    seeded_team_bullpen: Engine,
) -> None:
    sql = f"""
        WITH matchup_keys AS (
            SELECT
                990002 AS game_pk,
                DATE '2024-06-10' AS reference_date,
                4001 AS batter_id,
                9011 AS pitcher_id,
                TRUE AS is_historical,
                200 AS opp_team_id
        ),
        team_bp AS ({team_bullpen_sql()})
        SELECT * FROM team_bp
    """
    session_factory = sessionmaker(bind=seeded_team_bullpen, future=True, expire_on_commit=False)
    with session_factory() as s:
        row = s.execute(text(sql)).mappings().one()

    assert row["opp_team_id"] == 200
    assert row["opp_bp_hr_per_pa_30d"] == pytest.approx(0.0)
    assert row["opp_bp_barrel_pct_allowed_30d"] == pytest.approx(0.0)
