"""Pitcher pitch-mix SQL tests."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.features.pitcher_pitch_mix import pitch_mix_sql


def test_sql_has_expected_columns() -> None:
    sql = pitch_mix_sql()
    for c in [
        "game_pk",
        "batter_id",
        "pitcher_id",
        "reference_date",
        "p_ff_usage",
        "p_si_usage",
        "p_fc_usage",
        "p_sl_usage",
        "p_cu_usage",
        "p_ch_usage",
        "p_fs_usage",
        "p_ff_velo_avg",
        "p_primary_pitch",
    ]:
        assert c in sql, f"missing column {c}"


def test_sql_strict_less_than_reference_date() -> None:
    import re

    assert re.search(r"<=\s*[a-z_.]*reference_date", pitch_mix_sql(), re.IGNORECASE) is None


@pytest.fixture()
def seeded_pitch_mix(test_engine: Engine, clean_tables) -> Engine:
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text("INSERT INTO parks (park_id, name) VALUES (78001, 'tp') ON CONFLICT DO NOTHING")
        )
        # Pitcher 780001: 100 FF at 94 mph, 50 SL at 85 mph, on 2024-06-01.
        for i in range(100):
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    " pitch_type, release_speed) "
                    "VALUES ('2024-06-01', :gp, 1, 1, 780100, 780001, 'FF', 94.0)"
                ),
                {"gp": 7800000 + i},
            )
        for i in range(50):
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    " pitch_type, release_speed) "
                    "VALUES ('2024-06-01', :gp, 2, 1, 780100, 780001, 'SL', 85.0)"
                ),
                {"gp": 7800200 + i},
            )
        s.commit()
    return test_engine


@pytest.mark.integration
def test_pitch_mix_computes_usage_and_velo(seeded_pitch_mix: Engine) -> None:
    sql = f"""
        WITH matchup_keys AS (
            SELECT 1 AS game_pk, 780100 AS batter_id, 780001 AS pitcher_id,
                   DATE '2024-08-01' AS reference_date
        ),
        pm AS ({pitch_mix_sql()})
        SELECT * FROM pm
    """
    session_factory = sessionmaker(bind=seeded_pitch_mix, future=True, expire_on_commit=False)
    with session_factory() as s:
        row = s.execute(text(sql)).mappings().one()

    # 100 FF / 150 total = 0.667; 50 SL / 150 = 0.333
    assert row["p_ff_usage"] == pytest.approx(0.667, abs=0.01)
    assert row["p_sl_usage"] == pytest.approx(0.333, abs=0.01)
    assert row["p_si_usage"] == pytest.approx(0.0, abs=0.01)
    assert row["p_ff_velo_avg"] == pytest.approx(94.0, abs=0.1)
    assert row["p_primary_pitch"] == "FF"
