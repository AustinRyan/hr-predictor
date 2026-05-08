"""The core Phase 3 non-negotiable: feature rows for a PA on date D use
no data from D or later. Any regression here breaks the predictor's
training signal.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.features.builder import build_features_for_game


@pytest.fixture()
def leakage_setup(test_engine: Engine, clean_tables) -> Iterator[Engine]:
    """Seed a synthetic clobber scenario designed to trip any leakage bug.

    Batter 888001 has 2 prior-PA launch_speeds and one clobber PA on the target date:
      2024-06-01  game=888001  batter=888001  pitcher=888002  launch_speed=80
      2024-06-15  game=888002  batter=888001  pitcher=888002  launch_speed=90
      2024-07-04  game=888003  batter=888001  pitcher=888002  launch_speed=120 (HR!)  <- target game
    """
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text(
                "INSERT INTO parks (park_id, name, elevation_ft, orientation_deg, roof_type) "
                "VALUES (88801, 'tp', 100, 0.0, 'open') ON CONFLICT DO NOTHING"
            )
        )
        rows = [
            # (game_date, game_pk, launch_speed, launch_speed_angle, events)
            (date(2024, 6, 1), 888001, 80.0, 3, "single"),
            (date(2024, 6, 15), 888002, 90.0, 3, "single"),
            (date(2024, 7, 4), 888003, 120.0, 6, "home_run"),
        ]
        for gd, gpk, ls, lsa, ev in rows:
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    " stand, p_throws, launch_speed, launch_angle, launch_speed_angle, events, "
                    " estimated_woba_using_speedangle, estimated_ba_using_speedangle, "
                    " home_team, away_team, inning_topbot, pitch_type, release_speed, "
                    " bat_speed) "
                    "VALUES (:gd, :gp, 1, 1, 888001, 888002, 'R', 'R', :ls, 25.0, :lsa, "
                    " :ev, 0.4, 0.3, 'XXX', 'YYY', 'Top', 'FF', 94.0, 72.0)"
                ),
                {"gd": gd, "gp": gpk, "ls": ls, "lsa": lsa, "ev": ev},
            )
        # Stub game row for the target game (888003) so park join works.
        s.execute(
            text(
                "INSERT INTO games (game_pk, game_date, season, venue_id, home_team_id, "
                "away_team_id, status, day_night) "
                "VALUES (888003, '2024-07-04', 2024, 88801, 1, 2, 'Final', 'D')"
            )
        )
        s.commit()
    yield test_engine


@pytest.mark.integration
def test_target_game_features_exclude_target_game_data(leakage_setup: Engine) -> None:
    """After build, the feature row for game 888003 (the target) must not
    reflect the 120 mph clobber HR from that same game - features use
    only strictly-prior data.
    """
    written = build_features_for_game(888003, engine=leakage_setup)
    assert written >= 1

    session_factory = sessionmaker(bind=leakage_setup, future=True, expire_on_commit=False)
    with session_factory() as s:
        row = (
            s.execute(
                text(
                    "SELECT b_avg_ev_season, b_pa_count_season, b_hr_per_pa_season, hr_on_pa "
                    "FROM matchup_features "
                    "WHERE game_pk = 888003 AND batter_id = 888001 AND pitcher_id = 888002"
                )
            )
            .mappings()
            .one()
        )

    # Prior pitches: 80 + 90 = 170; mean = 85. The clobber (120) MUST NOT appear.
    assert row["b_avg_ev_season"] == pytest.approx(85.0, abs=0.5)
    assert row["b_pa_count_season"] == 2
    assert row["b_hr_per_pa_season"] == pytest.approx(0.0, abs=0.01)  # 0 HR in prior PAs
    # The LABEL, however, should be True - batter DID hit HR in this game.
    assert row["hr_on_pa"] is True


@pytest.fixture()
def team_bullpen_leakage_setup(test_engine: Engine, clean_tables) -> Iterator[Engine]:
    """Seed prior bullpen data plus a target-date reliever HR that must not leak."""
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text(
                "INSERT INTO parks (park_id, name, elevation_ft, orientation_deg, roof_type) "
                "VALUES (88901, 'team bp leakage park', 100, 0.0, 'open')"
            )
        )
        for game_pk, game_date in ((889001, "2024-06-01"), (889002, "2024-06-10")):
            s.execute(
                text(
                    "INSERT INTO games "
                    "(game_pk, game_date, season, venue_id, home_team_id, away_team_id, "
                    "status, day_night) "
                    "VALUES (:game_pk, :game_date, 2024, 88901, 100, 200, 'Final', 'D')"
                ),
                {"game_pk": game_pk, "game_date": game_date},
            )

        # Prior home starter + reliever. Prior reliever allows no HR.
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                "stand, p_throws, inning, inning_topbot, launch_speed, "
                "launch_speed_angle, events) "
                "VALUES ('2024-06-01', 889001, 1, 1, 6001, 7001, 'L', 'R', "
                "1, 'Top', 80.0, 2, 'single')"
            )
        )
        for ab in (10, 11):
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    "stand, p_throws, inning, inning_topbot, launch_speed, "
                    "launch_speed_angle, events) "
                    "VALUES ('2024-06-01', 889001, :ab, 1, :batter, 7002, 'L', 'R', "
                    "7, 'Top', 90.0, 3, 'single')"
                ),
                {"ab": ab, "batter": 6100 + ab},
            )

        # Target starter matchup row plus a target-date home reliever HR.
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                "stand, p_throws, inning, inning_topbot, launch_speed, "
                "launch_speed_angle, events) "
                "VALUES ('2024-06-10', 889002, 1, 1, 6001, 7001, 'L', 'R', "
                "1, 'Top', 85.0, 2, 'single')"
            )
        )
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                "stand, p_throws, inning, inning_topbot, launch_speed, "
                "launch_speed_angle, events) "
                "VALUES ('2024-06-10', 889002, 10, 1, 6002, 7002, 'L', 'R', "
                "7, 'Top', 115.0, 6, 'home_run')"
            )
        )
        s.commit()
    yield test_engine


@pytest.mark.integration
def test_team_bullpen_features_exclude_target_date_relief_hrs(
    team_bullpen_leakage_setup: Engine,
) -> None:
    written = build_features_for_game(889002, engine=team_bullpen_leakage_setup)
    assert written >= 1

    session_factory = sessionmaker(
        bind=team_bullpen_leakage_setup,
        future=True,
        expire_on_commit=False,
    )
    with session_factory() as s:
        row = (
            s.execute(
                text(
                    "SELECT opp_team_id, opp_bp_hr_per_pa_30d "
                    "FROM matchup_features "
                    "WHERE game_pk = 889002 AND batter_id = 6001 AND pitcher_id = 7001"
                )
            )
            .mappings()
            .one()
        )

    assert row["opp_team_id"] == 100
    assert row["opp_bp_hr_per_pa_30d"] == pytest.approx(0.0)
