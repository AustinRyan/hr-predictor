"""End-to-end smoke tests for the feature builder."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.features.builder import (
    backfill_team_bullpen_features,
    build_features_for_date,
    build_features_for_game,
)


@pytest.fixture()
def leakage_setup(test_engine: Engine, clean_tables) -> Iterator[Engine]:
    """Mirror of the leakage fixture - pragmatic copy-paste, per task guidance."""
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text(
                "INSERT INTO parks (park_id, name, elevation_ft, orientation_deg, roof_type) "
                "VALUES (88801, 'tp', 100, 0.0, 'open') ON CONFLICT DO NOTHING"
            )
        )
        rows = [
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
def test_build_idempotent_on_rerun(leakage_setup: Engine) -> None:
    """Re-running for the same game produces the same row count."""
    first = build_features_for_game(888003, engine=leakage_setup)
    second = build_features_for_game(888003, engine=leakage_setup)

    session_factory = sessionmaker(bind=leakage_setup, future=True, expire_on_commit=False)
    with session_factory() as s:
        total = s.execute(
            text("SELECT COUNT(*) FROM matchup_features WHERE game_pk = 888003")
        ).scalar_one()

    assert first == second
    assert total == first  # not doubled


@pytest.mark.integration
def test_build_populates_expected_row_shape(leakage_setup: Engine) -> None:
    """A built row has correct keys + at least some non-null features + label."""
    build_features_for_game(888003, engine=leakage_setup)

    session_factory = sessionmaker(bind=leakage_setup, future=True, expire_on_commit=False)
    with session_factory() as s:
        row = (
            s.execute(
                text(
                    "SELECT game_date, is_historical, hr_on_pa, b_pa_count_season, "
                    "park_id, park_elevation_ft "
                    "FROM matchup_features WHERE game_pk = 888003 LIMIT 1"
                )
            )
            .mappings()
            .one()
        )

    assert row["is_historical"] is True
    assert row["hr_on_pa"] is not None  # populated label
    assert row["b_pa_count_season"] is not None  # at least one batter feature
    assert row["park_id"] == 88801  # park link resolved
    assert row["park_elevation_ft"] == 100


@pytest.mark.integration
def test_build_for_unknown_game_returns_zero(test_engine: Engine, clean_tables) -> None:
    """Game with no statcast rows + no daily_schedule row -> 0 written."""
    written = build_features_for_game(999999999, engine=test_engine)
    assert written == 0


@pytest.mark.integration
def test_build_features_for_historical_iterates_days(leakage_setup: Engine) -> None:
    """Day-by-day iterator picks up game_pks from statcast_pitches.

    The leakage_setup fixture seeds one game on 2024-07-04; a range over
    that day should discover it and produce a matchup row.
    """
    from src.features.builder import build_features_for_historical

    total = build_features_for_historical(date(2024, 7, 4), date(2024, 7, 4), engine=leakage_setup)
    assert total >= 1

    session_factory = sessionmaker(bind=leakage_setup, future=True, expire_on_commit=False)
    with session_factory() as s:
        count = s.execute(
            text("SELECT COUNT(*) FROM matchup_features WHERE game_pk = 888003")
        ).scalar_one()
    assert count >= 1


@pytest.mark.integration
def test_build_features_for_today_no_schedule(test_engine: Engine, clean_tables) -> None:
    """Empty daily_schedule -> 0 (smoke test for the today-path entry point)."""
    from src.features.builder import build_features_for_today

    assert build_features_for_today(engine=test_engine) == 0


@pytest.mark.integration
def test_future_build_prunes_stale_probable_pitcher_rows(
    test_engine: Engine,
    clean_tables,
) -> None:
    """Probable-starter changes should not leave duplicate future matchups."""
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text(
                "INSERT INTO parks (park_id, name, elevation_ft, orientation_deg, roof_type) "
                "VALUES (99803, 'future park', 100, 0.0, 'open') ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO daily_schedule "
                "(game_pk, game_date, home_team_id, away_team_id, venue_id, "
                " game_start_utc, probable_home_pitcher_id, probable_away_pitcher_id, status) "
                "VALUES (9991001, '2026-04-23', 1, 2, 99803, NOW(), 1111, 2222, 'Scheduled')"
            )
        )
        s.execute(
            text(
                "INSERT INTO projected_lineups "
                "(game_pk, team_id, batter_id, batting_order, is_confirmed) "
                "VALUES "
                "(9991001, 2, 9001, 1, FALSE), "
                "(9991001, 1, 9002, 1, FALSE)"
            )
        )
        s.execute(
            text(
                "INSERT INTO matchup_features "
                "(game_date, game_pk, batter_id, pitcher_id, is_historical, park_id, "
                " ctx_projected_pa) "
                "VALUES ('2026-04-23', 9991001, 9001, 3333, FALSE, 99803, 4.6)"
            )
        )
        s.commit()

    written = build_features_for_date(date(2026, 4, 23), engine=test_engine)

    with session_factory() as s:
        rows = (
            s.execute(
                text(
                    "SELECT batter_id, pitcher_id "
                    "FROM matchup_features "
                    "WHERE game_pk = 9991001 "
                    "ORDER BY batter_id, pitcher_id"
                )
            )
            .mappings()
            .all()
        )

    assert written == 2
    assert [dict(row) for row in rows] == [
        {"batter_id": 9001, "pitcher_id": 1111},
        {"batter_id": 9002, "pitcher_id": 2222},
    ]


@pytest.mark.integration
def test_builder_populates_team_bullpen_features(test_engine: Engine, clean_tables) -> None:
    """Future rows attach the opponent team's relief-only bullpen profile."""
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text(
                "INSERT INTO parks (park_id, name, elevation_ft, orientation_deg, roof_type) "
                "VALUES (99901, 'team bullpen park', 100, 0.0, 'open')"
            )
        )
        s.execute(
            text(
                "INSERT INTO games "
                "(game_pk, game_date, season, venue_id, home_team_id, away_team_id, status) "
                "VALUES (9992001, '2024-06-01', 2024, 99901, 100, 200, 'Final')"
            )
        )
        s.execute(
            text(
                "INSERT INTO daily_schedule "
                "(game_pk, game_date, home_team_id, away_team_id, venue_id, "
                " game_start_utc, probable_home_pitcher_id, probable_away_pitcher_id, status) "
                "VALUES (9992002, '2024-06-10', 100, 200, 99901, NOW(), 9001, 9011, "
                "'Scheduled')"
            )
        )
        s.execute(
            text(
                "INSERT INTO projected_lineups "
                "(game_pk, team_id, batter_id, batting_order, is_confirmed) "
                "VALUES "
                "(9992002, 200, 5001, 1, FALSE), "
                "(9992002, 100, 5002, 1, FALSE)"
            )
        )
        # Home team 100 starter + reliever. Top-half means home team is pitching.
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                "inning, inning_topbot, stand, launch_speed, launch_speed_angle, events) "
                "VALUES ('2024-06-01', 9992001, 1, 1, 5101, 9001, "
                "1, 'Top', 'L', 80.0, 2, 'single')"
            )
        )
        for ab, event in ((10, "home_run"), (11, "single")):
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    "inning, inning_topbot, stand, launch_speed, launch_speed_angle, events) "
                    "VALUES ('2024-06-01', 9992001, :ab, 1, :batter, 9002, "
                    "7, 'Top', 'L', 100.0, 6, :event)"
                ),
                {"ab": ab, "batter": 5100 + ab, "event": event},
            )
        # Away team 200 starter + reliever. Bottom-half means away team is pitching.
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                "inning, inning_topbot, stand, launch_speed, launch_speed_angle, events) "
                "VALUES ('2024-06-01', 9992001, 20, 1, 5201, 9011, "
                "1, 'Bot', 'R', 80.0, 2, 'single')"
            )
        )
        for ab in (30, 31):
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    "inning, inning_topbot, stand, launch_speed, launch_speed_angle, events) "
                    "VALUES ('2024-06-01', 9992001, :ab, 1, :batter, 9012, "
                    "7, 'Bot', 'R', 82.0, 2, 'single')"
                ),
                {"ab": ab, "batter": 5200 + ab},
            )
        s.commit()

    written = build_features_for_date(date(2024, 6, 10), engine=test_engine)

    with session_factory() as s:
        rows = (
            s.execute(
                text(
                    "SELECT batter_id, pitcher_id, opp_team_id, opp_bp_hr_per_pa_30d "
                    "FROM matchup_features "
                    "WHERE game_pk = 9992002 "
                    "ORDER BY batter_id"
                )
            )
            .mappings()
            .all()
        )

    assert written == 2
    assert [dict(row) for row in rows] == [
        {
            "batter_id": 5001,
            "pitcher_id": 9001,
            "opp_team_id": 100,
            "opp_bp_hr_per_pa_30d": pytest.approx(0.5),
        },
        {
            "batter_id": 5002,
            "pitcher_id": 9011,
            "opp_team_id": 200,
            "opp_bp_hr_per_pa_30d": pytest.approx(0.0),
        },
    ]


@pytest.mark.integration
def test_backfill_team_bullpen_updates_existing_rows(test_engine: Engine, clean_tables) -> None:
    """Bullpen-only mode should repair existing matchup rows without a full rebuild."""
    test_builder_populates_team_bullpen_features(test_engine, clean_tables)

    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text(
                "UPDATE matchup_features "
                "SET opp_team_id = NULL, opp_bp_hr_per_pa_30d = NULL "
                "WHERE game_pk = 9992002"
            )
        )
        s.commit()

    updated = backfill_team_bullpen_features(
        date(2024, 6, 10),
        date(2024, 6, 10),
        engine=test_engine,
    )

    with session_factory() as s:
        rows = (
            s.execute(
                text(
                    "SELECT batter_id, opp_team_id, opp_bp_hr_per_pa_30d "
                    "FROM matchup_features "
                    "WHERE game_pk = 9992002 "
                    "ORDER BY batter_id"
                )
            )
            .mappings()
            .all()
        )

    assert updated == 2
    assert [dict(row) for row in rows] == [
        {
            "batter_id": 5001,
            "opp_team_id": 100,
            "opp_bp_hr_per_pa_30d": pytest.approx(0.5),
        },
        {
            "batter_id": 5002,
            "opp_team_id": 200,
            "opp_bp_hr_per_pa_30d": pytest.approx(0.0),
        },
    ]


@pytest.mark.integration
def test_day_batched_builds_multiple_games_in_one_pass(leakage_setup) -> None:
    """Seed two synthetic games on the same day, verify both land via the day path."""
    from src.features.builder import build_features_for_historical

    session_factory = sessionmaker(bind=leakage_setup, future=True, expire_on_commit=False)
    with session_factory() as s:
        # Seed a second game on 2024-07-04.
        s.execute(
            text(
                "INSERT INTO games (game_pk, game_date, season, venue_id, home_team_id, "
                "away_team_id, status, day_night) "
                "VALUES (888004, '2024-07-04', 2024, 88801, 1, 2, 'Final', 'N')"
            )
        )
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                " stand, p_throws, launch_speed, events, "
                " estimated_woba_using_speedangle, inning_topbot) "
                "VALUES ('2024-07-04', 888004, 1, 1, 888005, 888006, 'L', 'R', 95.0, "
                " 'single', 0.4, 'Top')"
            )
        )
        s.commit()

    written = build_features_for_historical(
        date(2024, 7, 4), date(2024, 7, 4), engine=leakage_setup
    )
    assert written >= 2  # At least one row per game

    with session_factory() as s:
        rows = s.execute(
            text(
                "SELECT COUNT(DISTINCT game_pk) FROM matchup_features "
                "WHERE game_date = '2024-07-04'"
            )
        ).scalar_one()
    assert rows == 2
