"""Pitcher profile + TTO tests."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.features.pitcher_profile import (
    pitcher_profile_sql,
    tto_multiplier,
    tto_penalty_for,
)

# ---------- TTO ----------


def test_tto_multiplier_exact_values() -> None:
    assert tto_multiplier(1) == pytest.approx(1.00)
    assert tto_multiplier(2) == pytest.approx(1.05)
    assert tto_multiplier(3) == pytest.approx(1.20)
    assert tto_multiplier(4) is None
    assert tto_multiplier(5) is None
    # Zero / negative treated as 1st PA (conservative).
    assert tto_multiplier(0) == pytest.approx(1.00)
    assert tto_multiplier(-1) == pytest.approx(1.00)


def test_tto_penalty_4_2_pa_averages_starter_only() -> None:
    # Starter PAs 1..3 get 1.00, 1.05, 1.20; PAs 4 and 0.2 of PA 5 are bullpen → dropped.
    # Avg = (1.00 + 1.05 + 1.20) / 3 = 1.0833.
    assert tto_penalty_for(4.2) == pytest.approx(1.0833, abs=0.005)


def test_tto_penalty_3_0_pa_full_starter() -> None:
    # Exactly 3 PAs: (1.00 + 1.05 + 1.20) / 3 = 1.0833.
    assert tto_penalty_for(3.0) == pytest.approx(1.0833, abs=0.005)


def test_tto_penalty_1_0_pa() -> None:
    # Single PA → 1.00.
    assert tto_penalty_for(1.0) == pytest.approx(1.00, abs=0.001)


def test_tto_penalty_2_5_pa() -> None:
    # 1.00 + 1.05 + 0.5 * 1.20 = 2.05 + 0.6 = 2.65 / (1 + 1 + 0.5) = 2.65 / 2.5 = 1.06
    assert tto_penalty_for(2.5) == pytest.approx(1.06, abs=0.005)


def test_tto_penalty_zero_pa_returns_neutral() -> None:
    assert tto_penalty_for(0.0) == pytest.approx(1.0)


# ---------- SQL ----------


def test_sql_has_expected_columns() -> None:
    sql = pitcher_profile_sql()
    for c in [
        "game_pk",
        "batter_id",
        "pitcher_id",
        "reference_date",
        "p_hr_per_9_season",
        "p_hr_per_9_career",
        "p_barrel_pct_allowed_season",
        "p_hardhit_pct_allowed_season",
        "p_fb_pct",
        "p_gb_pct",
        "p_k_pct",
        "p_bb_pct",
        "p_vs_lhb_xwoba_allowed",
        "p_vs_rhb_xwoba_allowed",
        "p_vs_lhb_hr_rate",
        "p_vs_rhb_hr_rate",
    ]:
        assert c in sql, f"missing column {c}"


def test_sql_uses_strict_less_than_reference_date() -> None:
    import re

    sql = pitcher_profile_sql()
    assert re.search(r"<=\s*[a-z_.]*reference_date", sql, re.IGNORECASE) is None


@pytest.fixture()
def seeded_pitcher_data(test_engine: Engine, clean_tables) -> Engine:
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text("INSERT INTO parks (park_id, name) VALUES (77901, 'tp') " "ON CONFLICT DO NOTHING")
        )
        # Pitcher 779001 faces 20 PAs in 2024:
        #   10 PAs vs R: 1 HR, 3 Ks, 1 BB, 5 balls-in-play (3 with LA=15, 2 with LA=30)
        #   10 PAs vs L: 0 HR, 2 Ks, 0 BB, 8 balls-in-play (4 LA=5 GB, 4 LA=28 FB)
        # Expected season stats (rough):
        #   HR/9 = (1 HR / 20 PA) * 38.7 ≈ 1.935
        #   k_pct = 5/20 = 0.25
        #   bb_pct = 1/20 = 0.05
        # vs_R: 1 HR / 10 PA = 0.10
        # vs_L: 0 HR / 10 PA = 0.00
        # fb_pct (angle > 25): 2 (R) + 4 (L) = 6 out of 13 BIP = ~0.46
        # gb_pct (angle < 10): 4 (L) = 4 out of 13 BIP = ~0.31

        counter = 0
        for i in range(10):  # vs R
            counter += 1
            if i < 1:
                ev = "home_run"
                la = 30.0
                ls = 110.0
            elif i < 4:
                ev = "strikeout"
                la = None
                ls = None
            elif i == 4:
                ev = "walk"
                la = None
                ls = None
            elif i < 7:
                ev = "single"
                la = 15.0
                ls = 92.0
            else:
                ev = "double"
                la = 30.0
                ls = 100.0
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    " stand, launch_speed, launch_angle, launch_speed_angle, events, "
                    " estimated_woba_using_speedangle) "
                    "VALUES (:gd, :gp, 1, 1, 779100, 779001, 'R', :ls, :la, "
                    " :lsa, :ev, 0.4)"
                ),
                {
                    "gd": date(2024, 6, 1),
                    "gp": 7790000 + counter,
                    "ls": ls,
                    "la": la,
                    "lsa": 6 if ev == "home_run" else None,
                    "ev": ev,
                },
            )
        for i in range(10):  # vs L
            counter += 1
            if i < 2:
                ev = "strikeout"
                la = None
                ls = None
            elif i < 6:
                ev = "groundout"
                la = 5.0
                ls = 85.0
            else:
                ev = "flyout"
                la = 28.0
                ls = 90.0
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    " stand, launch_speed, launch_angle, launch_speed_angle, events, "
                    " estimated_woba_using_speedangle) "
                    "VALUES (:gd, :gp, 1, 1, 779101, 779001, 'L', :ls, :la, "
                    " NULL, :ev, 0.35)"
                ),
                {
                    "gd": date(2024, 6, 1),
                    "gp": 7790000 + counter,
                    "ls": ls,
                    "la": la,
                    "ev": ev,
                },
            )
        s.commit()
    return test_engine


@pytest.mark.integration
def test_pitcher_profile_computes_season_stats(seeded_pitcher_data: Engine) -> None:
    sql = f"""
        WITH matchup_keys AS (
            SELECT 1 AS game_pk, 779100 AS batter_id, 779001 AS pitcher_id,
                   DATE '2024-08-01' AS reference_date
        ),
        pp AS ({pitcher_profile_sql()})
        SELECT * FROM pp
    """
    session_factory = sessionmaker(bind=seeded_pitcher_data, future=True, expire_on_commit=False)
    with session_factory() as s:
        row = s.execute(text(sql)).mappings().one()

    # 1 HR / 20 PA → 0.05 HR/PA * 38.7 ≈ 1.935 HR/9
    assert row["p_hr_per_9_season"] == pytest.approx(1.935, abs=0.2)
    # K rate: 5 Ks / 20 PA = 0.25
    assert row["p_k_pct"] == pytest.approx(0.25, abs=0.01)
    # BB rate: 1 / 20 = 0.05
    assert row["p_bb_pct"] == pytest.approx(0.05, abs=0.01)
    # Handedness HR rates: 1/10 vs R, 0/10 vs L
    assert row["p_vs_rhb_hr_rate"] == pytest.approx(0.10, abs=0.01)
    assert row["p_vs_lhb_hr_rate"] == pytest.approx(0.0, abs=0.01)
