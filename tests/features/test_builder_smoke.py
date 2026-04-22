"""End-to-end smoke tests for the feature builder."""

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
