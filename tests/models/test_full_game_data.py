"""Tests for full-game HR training data assembly."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.models.full_game_data import FULL_GAME_FEATURE_COLUMNS, load_full_game_training_data


@pytest.fixture()
def seeded_full_game_training_data(test_engine: Engine, clean_tables) -> Engine:
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(text("INSERT INTO parks (park_id, name) VALUES (77101, 'full game park')"))
        s.execute(
            text(
                "INSERT INTO games "
                "(game_pk, game_date, season, venue_id, home_team_id, away_team_id, status) "
                "VALUES (771001, '2024-06-10', 2024, 77101, 100, 200, 'Final')"
            )
        )

        # Away batter 6101 faces the home starter, then homers off a reliever.
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                "inning, inning_topbot, stand, launch_speed, launch_speed_angle, events) "
                "VALUES ('2024-06-10', 771001, 1, 1, 6101, 7001, "
                "1, 'Top', 'L', 82.0, 2, 'single')"
            )
        )
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                "inning, inning_topbot, stand, launch_speed, launch_speed_angle, events) "
                "VALUES ('2024-06-10', 771001, 9, 1, 6101, 7002, "
                "6, 'Top', 'L', 106.0, 6, 'home_run')"
            )
        )

        # Away batter 6102 does not homer.
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                "inning, inning_topbot, stand, launch_speed, launch_speed_angle, events) "
                "VALUES ('2024-06-10', 771001, 2, 1, 6102, 7001, "
                "1, 'Top', 'R', 85.0, 3, 'single')"
            )
        )
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                "inning, inning_topbot, stand, launch_speed, launch_speed_angle, events) "
                "VALUES ('2024-06-10', 771001, 10, 1, 6102, 7002, "
                "6, 'Top', 'R', 78.0, 2, 'field_out')"
            )
        )

        # Feature rows exist for starter and reliever matchups; loader must pick starter rows.
        s.execute(
            text(
                "INSERT INTO matchup_features "
                "(game_date, game_pk, batter_id, pitcher_id, is_historical, hr_on_pa, "
                "b_hr_per_pa_season, p_hr_per_9_season, opp_bp_hr_per_pa_30d) "
                "VALUES "
                "('2024-06-10', 771001, 6101, 7001, TRUE, FALSE, 0.11, 1.1, 0.07), "
                "('2024-06-10', 771001, 6101, 7002, TRUE, TRUE, 0.99, 9.9, 0.77), "
                "('2024-06-10', 771001, 6102, 7001, TRUE, FALSE, 0.22, 1.2, 0.08), "
                "('2024-06-10', 771001, 6102, 7002, TRUE, FALSE, 0.88, 8.8, 0.78)"
            )
        )
        s.commit()
    return test_engine


@pytest.mark.integration
def test_load_full_game_training_data_uses_starter_row_and_full_game_label(
    seeded_full_game_training_data: Engine,
) -> None:
    frame = load_full_game_training_data(
        date(2024, 6, 10),
        date(2024, 6, 10),
        engine=seeded_full_game_training_data,
    )

    assert len(frame.X) == 2
    assert frame.metadata["batter_id"].tolist() == [6101, 6102]
    assert frame.metadata["starter_pitcher_id"].tolist() == [7001, 7001]
    assert frame.y.tolist() == [1, 0]
    assert frame.dates.tolist() == [date(2024, 6, 10), date(2024, 6, 10)]

    assert frame.X["b_hr_per_pa_season"].tolist() == [pytest.approx(0.11), pytest.approx(0.22)]
    assert frame.X["p_hr_per_9_season"].tolist() == [pytest.approx(1.1), pytest.approx(1.2)]
    assert frame.X["opp_bp_hr_per_pa_30d"].tolist() == [
        pytest.approx(0.07),
        pytest.approx(0.08),
    ]
    assert "opp_team_id" not in FULL_GAME_FEATURE_COLUMNS
