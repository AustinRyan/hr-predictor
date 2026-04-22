"""Platoon split + pitch-type matrix tests."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.features.batter_splits import (
    DEFAULT_LEAGUE_AVG_HR_PER_PA,
    LEAGUE_AVG_HR_PER_PA,
    pitch_type_matrix_sql,
    platoon_splits_sql,
    regress_rate,
)


def test_league_avg_covers_training_years() -> None:
    for year in [2021, 2022, 2023, 2024]:
        assert year in LEAGUE_AVG_HR_PER_PA, f"missing league avg for {year}"


def test_default_league_avg_is_sane() -> None:
    assert 0.02 <= DEFAULT_LEAGUE_AVG_HR_PER_PA <= 0.035


def test_regress_rate_small_sample_moves_to_mean() -> None:
    # 20 PA with observed 30% HR rate, league 3%, weight 100 ->
    # regressed = (0.30*20 + 0.03*100) / (20+100) = (6 + 3) / 120 = 0.075
    assert regress_rate(0.30, 20, 0.03, regression_weight=100) == pytest.approx(0.075, abs=1e-4)


def test_regress_rate_large_sample_stays_close() -> None:
    # 500 PA with 10% observed, league 3%, weight 100 ->
    # (0.10*500 + 0.03*100) / 600 = (50 + 3) / 600 = 0.0883
    assert regress_rate(0.10, 500, 0.03, regression_weight=100) == pytest.approx(0.0883, abs=1e-3)


def test_regress_rate_zero_sample_returns_mean() -> None:
    assert regress_rate(0.0, 0, 0.03, regression_weight=100) == pytest.approx(0.03, abs=1e-6)


def test_regress_rate_custom_weight() -> None:
    # Lower weight = less regression.
    result = regress_rate(0.30, 20, 0.03, regression_weight=20)
    # (0.30*20 + 0.03*20)/(20+20) = (6+0.6)/40 = 0.165
    assert result == pytest.approx(0.165, abs=1e-4)


def test_platoon_sql_returns_string_with_expected_columns() -> None:
    sql = platoon_splits_sql()
    expected_cols = [
        "b_vs_lhp_barrel_pct",
        "b_vs_rhp_barrel_pct",
        "b_vs_lhp_xwoba",
        "b_vs_rhp_xwoba",
        "b_vs_lhp_hr_per_pa",
        "b_vs_rhp_hr_per_pa",
        "b_vs_lhp_hr_per_pa_reg",
        "b_vs_rhp_hr_per_pa_reg",
        "b_vs_lhp_pa_count",
        "b_vs_rhp_pa_count",
    ]
    for c in expected_cols:
        assert c in sql, f"missing column {c} in platoon SQL"
    assert "matchup_keys" in sql.lower()


def test_platoon_sql_uses_strict_less_than_reference_date() -> None:
    import re

    sql = platoon_splits_sql()
    assert re.search(r"<=\s*[a-z_.]*reference_date", sql, re.IGNORECASE) is None


def test_pitch_type_sql_covers_all_7_types() -> None:
    sql = pitch_type_matrix_sql()
    for pt in ["ff", "si", "fc", "sl", "cu", "ch", "fs"]:
        assert f"b_xwoba_vs_{pt}" in sql, f"missing b_xwoba_vs_{pt}"
        assert f"b_hr_rate_vs_{pt}" in sql, f"missing b_hr_rate_vs_{pt}"
        assert f"b_pa_count_vs_{pt}" in sql, f"missing b_pa_count_vs_{pt}"


@pytest.fixture()
def seeded_platoon_data(test_engine: Engine, clean_tables) -> Engine:
    """Batter 777101 faces some LHPs and RHPs in 2024."""
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text("INSERT INTO parks (park_id, name) VALUES (77710, 'tp') " "ON CONFLICT DO NOTHING")
        )
        # 10 PAs vs RHP (2 HR), 5 PAs vs LHP (0 HR), all in 2024.
        # For PA distinctness, give unique (game_pk, at_bat_number) per pitch.
        for i in range(10):
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    " p_throws, launch_speed, launch_speed_angle, events, "
                    " estimated_woba_using_speedangle, pitch_type) "
                    "VALUES (:gd, :gp, :ab, 1, 777101, 777102, 'R', 95.0, 6, :ev, "
                    " 0.4, 'FF')"
                ),
                {
                    "gd": date(2024, 6, 1 + i % 28),
                    "gp": 7710000 + i,
                    "ab": 1,
                    "ev": "home_run" if i < 2 else "single",
                },
            )
        for i in range(5):
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    " p_throws, launch_speed, launch_speed_angle, events, "
                    " estimated_woba_using_speedangle, pitch_type) "
                    "VALUES (:gd, :gp, :ab, 1, 777101, 777103, 'L', 88.0, 4, 'strikeout', "
                    " 0.0, 'SL')"
                ),
                {"gd": date(2024, 7, 1 + i), "gp": 7710100 + i, "ab": 1},
            )
        s.commit()
    return test_engine


@pytest.mark.integration
def test_platoon_sql_computes_raw_and_regressed(seeded_platoon_data: Engine) -> None:
    sql = f"""
        WITH matchup_keys AS (
            SELECT 1 AS game_pk, 777101 AS batter_id, DATE '2024-08-01' AS reference_date
        ),
        platoon AS (
            {platoon_splits_sql()}
        )
        SELECT * FROM platoon
    """
    session_factory = sessionmaker(bind=seeded_platoon_data, future=True, expire_on_commit=False)
    with session_factory() as s:
        row = s.execute(text(sql)).mappings().one()

    # vs RHP: 10 PAs, 2 HR -> raw = 0.2
    assert row["b_vs_rhp_pa_count"] == 10
    assert row["b_vs_rhp_hr_per_pa"] == pytest.approx(0.2, abs=0.01)
    # Regressed with weight=100, league 2024 ~0.0286 ->
    # (0.2*10 + 0.0286*100)/(10+100) = (2+2.86)/110 ~= 0.044
    assert row["b_vs_rhp_hr_per_pa_reg"] == pytest.approx(0.044, abs=0.005)

    # vs LHP: 5 PAs, 0 HR -> raw = 0, regressed toward league average
    assert row["b_vs_lhp_pa_count"] == 5
    assert row["b_vs_lhp_hr_per_pa"] == pytest.approx(0.0, abs=0.01)
    # (0*5 + 0.0286*100)/(5+100) = 2.86/105 ~= 0.0272
    assert row["b_vs_lhp_hr_per_pa_reg"] == pytest.approx(0.0272, abs=0.005)


@pytest.mark.integration
def test_pitch_type_sql_aggregates_by_type(seeded_platoon_data: Engine) -> None:
    sql = f"""
        WITH matchup_keys AS (
            SELECT 1 AS game_pk, 777101 AS batter_id, DATE '2024-08-01' AS reference_date
        ),
        ptm AS (
            {pitch_type_matrix_sql()}
        )
        SELECT * FROM ptm
    """
    session_factory = sessionmaker(bind=seeded_platoon_data, future=True, expire_on_commit=False)
    with session_factory() as s:
        row = s.execute(text(sql)).mappings().one()

    # 10 FF pitches (all from RHP, 2 HR), 5 SL pitches (0 HR)
    assert row["b_pa_count_vs_ff"] == 10
    assert row["b_pa_count_vs_sl"] == 5
    assert row["b_hr_rate_vs_ff"] == pytest.approx(0.2, abs=0.01)
    assert row["b_hr_rate_vs_sl"] == pytest.approx(0.0, abs=0.01)
    # Not seen: FC, SI, CU, CH, FS -> PA count 0, rate NULL
    assert row["b_pa_count_vs_cu"] == 0
