"""Tests for batter rolling-window SQL generator."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.features.batter_rolling import rolling_features_sql


def test_sql_returns_non_empty_string() -> None:
    sql = rolling_features_sql()
    assert isinstance(sql, str)
    assert len(sql) > 100
    # Must be a SELECT expression referencing matchup_keys.
    assert "matchup_keys" in sql.lower()
    assert "select" in sql.lower()


def test_sql_references_expected_output_columns() -> None:
    sql = rolling_features_sql()
    expected = [
        "game_pk",
        "batter_id",
        "reference_date",
        "b_barrel_pct_7d",
        "b_barrel_pct_14d",
        "b_barrel_pct_30d",
        "b_barrel_pct_season",
        "b_hardhit_pct_7d",
        "b_avg_ev_7d",
        "b_p90_ev_7d",
        "b_avg_la_7d",
        "b_sweet_spot_pct_7d",
        "b_xwobacon_7d",
        "b_xiso_7d",
        "b_hr_per_pa_7d",
        "b_pa_count_7d",
        # spot checks across other windows
        "b_barrel_pct_season",
        "b_pa_count_season",
    ]
    for col in expected:
        assert col in sql, f"expected output column {col} missing from SQL"


def test_sql_uses_strict_less_than_reference_date() -> None:
    """Leakage guarantee — filters must use `< reference_date`, not `<=`."""
    import re

    sql = rolling_features_sql()
    # Any occurrence of `<=` applied to reference_date is a bug.
    leaky = re.search(r"<=\s*[a-z_.]*reference_date", sql, re.IGNORECASE)
    assert leaky is None, f"leakage guard violated: {leaky.group()}"


@pytest.fixture()
def seeded_rolling_data(test_engine: Engine, clean_tables) -> Engine:
    """Seed one synthetic batter (id=777001) with known pitches across
    dates designed to exercise each rolling window:
      - 2024-05-01: launch_speed 80, no barrel (old, only season picks up)
      - 2024-06-01: launch_speed 85, barrel (34d before ref=2024-07-05 -> 30d misses)
      - 2024-06-25: launch_speed 105, barrel (10d before ref -> 14d + 30d + season)
      - 2024-07-01: launch_speed 95, no barrel (4d before ref -> all windows)
      - 2024-07-05: launch_speed 120 (THE CLOBBER - on ref date itself, MUST NOT appear)
    Each pitch is its own PA (events populated, one per game).
    """
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        # Minimal park for FK on games if needed.
        s.execute(
            text("INSERT INTO parks (park_id, name) VALUES (77701, 'tp') " "ON CONFLICT DO NOTHING")
        )
        rows = [
            # (game_date, game_pk, launch_speed, launch_angle, launch_speed_angle, events)
            (date(2024, 5, 1), 7770001, 80.0, 15.0, 3, "single"),
            (date(2024, 6, 1), 7770002, 85.0, 25.0, 6, "double"),  # barrel
            (date(2024, 6, 25), 7770003, 105.0, 28.0, 6, "home_run"),  # barrel, HR
            (date(2024, 7, 1), 7770004, 95.0, 18.0, 5, "single"),
            (date(2024, 7, 5), 7770005, 120.0, 30.0, 6, "home_run"),  # CLOBBER on ref
        ]
        for game_date, game_pk, ev, la, lsa, events in rows:
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    " launch_speed, launch_angle, launch_speed_angle, events, "
                    " estimated_woba_using_speedangle, estimated_ba_using_speedangle) "
                    "VALUES (:gd, :gp, 1, 1, 777001, 777002, :ev, :la, :lsa, :ev_name, "
                    " 0.5, 0.3)"
                ),
                {
                    "gd": game_date,
                    "gp": game_pk,
                    "ev": ev,
                    "la": la,
                    "lsa": lsa,
                    "ev_name": events,
                },
            )
        s.commit()
    return test_engine


@pytest.mark.integration
def test_rolling_aggregates_exclude_reference_date(seeded_rolling_data: Engine) -> None:
    """Leakage test: ref=2024-07-05 must NOT include the 2024-07-05 clobber."""
    sql = f"""
        WITH matchup_keys AS (
            SELECT 123 AS game_pk, 777001 AS batter_id, DATE '2024-07-05' AS reference_date
        ),
        batter_rolling AS (
            {rolling_features_sql()}
        )
        SELECT * FROM batter_rolling
    """
    session_factory = sessionmaker(bind=seeded_rolling_data, future=True, expire_on_commit=False)
    with session_factory() as s:
        row = s.execute(text(sql)).mappings().one()

    # Expected pitches in each window (strictly before 2024-07-05):
    # 7d:    2024-06-28..2024-07-04 -> only 2024-07-01 (95 EV, no barrel). PA count=1, barrel=0
    # 14d:   2024-06-21..2024-07-04 -> 2024-06-25 (105) + 2024-07-01 (95). PA count=2, barrel=1
    # 30d:   2024-06-05..2024-07-04 -> same as 14d. PA count=2, barrel=1
    # season: 2024-01-01..2024-07-04 -> all 4 historical pitches. PA count=4, barrel=2

    # The 2024-07-05 clobber (EV 120, barrel) MUST be excluded from all windows.
    assert row["b_avg_ev_7d"] == pytest.approx(95.0, abs=0.01)
    assert row["b_pa_count_7d"] == 1
    assert row["b_pa_count_14d"] == 2
    assert row["b_pa_count_30d"] == 2
    assert row["b_pa_count_season"] == 4

    # Barrel% over season: 2 barrels / 4 BIP = 0.5
    assert row["b_barrel_pct_season"] == pytest.approx(0.5, abs=0.01)

    # HR per PA over season: 1 HR / 4 PAs = 0.25
    assert row["b_hr_per_pa_season"] == pytest.approx(0.25, abs=0.01)

    # Avg EV over season: (80 + 85 + 105 + 95) / 4 = 91.25
    assert row["b_avg_ev_season"] == pytest.approx(91.25, abs=0.01)
    # If leakage happened, it would be (80+85+105+95+120)/5 = 97.0.
    assert row["b_avg_ev_season"] != pytest.approx(97.0, abs=0.01)


@pytest.mark.integration
def test_rolling_returns_nulls_for_batter_with_no_pa(
    seeded_rolling_data: Engine,
) -> None:
    """Unknown batter -> all metrics NULL, PA count 0."""
    sql = f"""
        WITH matchup_keys AS (
            SELECT 999 AS game_pk, 999999 AS batter_id, DATE '2024-07-05' AS reference_date
        ),
        batter_rolling AS (
            {rolling_features_sql()}
        )
        SELECT * FROM batter_rolling
    """
    session_factory = sessionmaker(bind=seeded_rolling_data, future=True, expire_on_commit=False)
    with session_factory() as s:
        row = s.execute(text(sql)).mappings().one()

    assert row["b_pa_count_7d"] == 0
    assert row["b_avg_ev_7d"] is None
    assert row["b_barrel_pct_7d"] is None


# ---------------------------------------------------------------------------
# Pulled-FB pct tests (hc_x/hc_y pull zones)
# ---------------------------------------------------------------------------


def _insert_pitch(
    session,
    *,
    batter: int,
    game_date: date,
    game_pk: int,
    at_bat: int,
    stand: str | None,
    launch_angle: float | None,
    launch_speed: float | None,
    hc_x: float | None,
    events: str = "single",
) -> None:
    """Tiny helper to seed a single statcast_pitches row for pulled-FB tests."""
    session.execute(
        text(
            "INSERT INTO statcast_pitches "
            "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
            " stand, launch_speed, launch_angle, hc_x, events) "
            "VALUES (:gd, :gp, :ab, 1, :bat, 999999, :stand, :ls, :la, :hcx, :ev)"
        ),
        {
            "gd": game_date,
            "gp": game_pk,
            "ab": at_bat,
            "bat": batter,
            "stand": stand,
            "ls": launch_speed,
            "la": launch_angle,
            "hcx": hc_x,
            "ev": events,
        },
    )


@pytest.fixture()
def seeded_pulled_fb_data(test_engine: Engine, clean_tables) -> Engine:
    """Synthetic R-handed batter 880001 with known FBs.

    Reference date: 2024-06-05. Six pitches seeded pre-ref:
      2024-06-01: launch_angle=30, hc_x=60   -> pulled (LF, R)
      2024-06-01: launch_angle=28, hc_x=180  -> oppo (RF, R)  [not pulled]
      2024-06-02: launch_angle=30, hc_x=70   -> pulled (LF, R)
      2024-06-03: launch_angle=30, hc_x=130  -> center (~hc_x=125.42) [not pulled]
      2024-06-03: launch_angle=15, hc_x=50   -> NOT a FB (la<=25) — excluded
      2024-06-04: launch_angle=35, hc_x=100  -> pulled (LF, R)

    Denominator (FB with launch_speed IS NOT NULL): 5 pitches are FB and
    have EV set. Pulled: 3.
    Expected: b_pulled_fb_pct_7d = 3 / 5 = 0.6
    """
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        # Fixtures: (game_date, game_pk, at_bat, launch_angle, hc_x, launch_speed)
        rows = [
            (date(2024, 6, 1), 8800001, 1, 30.0, 60.0, 95.0),
            (date(2024, 6, 1), 8800001, 2, 28.0, 180.0, 98.0),
            (date(2024, 6, 2), 8800002, 1, 30.0, 70.0, 100.0),
            (date(2024, 6, 3), 8800003, 1, 30.0, 130.0, 92.0),
            (date(2024, 6, 3), 8800003, 2, 15.0, 50.0, 85.0),  # not FB (la<=25)
            (date(2024, 6, 4), 8800004, 1, 35.0, 100.0, 105.0),
        ]
        for gd, gp, ab, la, hcx, ls in rows:
            _insert_pitch(
                s,
                batter=880001,
                game_date=gd,
                game_pk=gp,
                at_bat=ab,
                stand="R",
                launch_angle=la,
                launch_speed=ls,
                hc_x=hcx,
            )
        s.commit()
    return test_engine


@pytest.mark.integration
def test_pulled_fb_pct_r_handed(seeded_pulled_fb_data: Engine) -> None:
    """Right-handed batter: ``hc_x < 125.42`` is pulled."""
    sql = f"""
        WITH matchup_keys AS (
            SELECT 100 AS game_pk, 880001 AS batter_id, DATE '2024-06-05' AS reference_date
        ),
        batter_rolling AS (
            {rolling_features_sql()}
        )
        SELECT * FROM batter_rolling
    """
    session_factory = sessionmaker(bind=seeded_pulled_fb_data, future=True, expire_on_commit=False)
    with session_factory() as s:
        row = s.execute(text(sql)).mappings().one()

    # 5 FB total (la>25, EV set); 3 pulled (hc_x=60, 70, 100 for an R batter).
    # hc_x=180 is oppo; hc_x=130 is slightly RF-of-center (not pulled for R).
    # launch_angle=15 row is excluded (not a FB).
    assert row["b_pulled_fb_pct_7d"] == pytest.approx(3.0 / 5.0, abs=1e-6)
    # Window independence check: 14d/30d/season cover the same 5 FB.
    assert row["b_pulled_fb_pct_14d"] == pytest.approx(3.0 / 5.0, abs=1e-6)
    assert row["b_pulled_fb_pct_30d"] == pytest.approx(3.0 / 5.0, abs=1e-6)
    assert row["b_pulled_fb_pct_season"] == pytest.approx(3.0 / 5.0, abs=1e-6)


@pytest.mark.integration
def test_pulled_fb_pct_lhb_uses_opposite_side(test_engine: Engine, clean_tables) -> None:
    """Left-handed batter: ``hc_x > 125.42`` is pulled.

    Seed 3 FBs:
      hc_x=200 (pulled -- RF for L)
      hc_x=80  (oppo  -- LF for L; not pulled)
      hc_x=130 (center-RF -- pulled for L since > 125.42)

    Actually 130 > 125.42, so for L that IS pulled. Let's use 125 instead
    to get center (not pulled). We'll use: 200, 80, 125.
    Pulled for L: hc_x=200 -> 1 pulled out of 3 total FB. => 1/3 ≈ 0.333.
    """
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        rows = [
            # (game_date, game_pk, at_bat, launch_angle, hc_x, launch_speed)
            (date(2024, 6, 2), 8810001, 1, 30.0, 200.0, 95.0),  # pulled-RF for L
            (date(2024, 6, 3), 8810002, 1, 30.0, 80.0, 98.0),  # oppo-LF for L
            (
                date(2024, 6, 4),
                8810003,
                1,
                30.0,
                125.0,
                92.0,
            ),  # center (< 125.42, not pulled for L)
        ]
        for gd, gp, ab, la, hcx, ls in rows:
            _insert_pitch(
                s,
                batter=881001,
                game_date=gd,
                game_pk=gp,
                at_bat=ab,
                stand="L",
                launch_angle=la,
                launch_speed=ls,
                hc_x=hcx,
            )
        s.commit()

    sql = f"""
        WITH matchup_keys AS (
            SELECT 200 AS game_pk, 881001 AS batter_id, DATE '2024-06-05' AS reference_date
        ),
        batter_rolling AS (
            {rolling_features_sql()}
        )
        SELECT * FROM batter_rolling
    """
    with session_factory() as s:
        row = s.execute(text(sql)).mappings().one()

    assert row["b_pulled_fb_pct_7d"] == pytest.approx(1.0 / 3.0, abs=1e-6)


@pytest.mark.integration
def test_pulled_fb_pct_handles_null_hcx(test_engine: Engine, clean_tables) -> None:
    """NULL ``hc_x`` is excluded from BOTH numerator and denominator.

    Rationale: ~60% of Statcast FBs have NULL hc_x (foul FBs, pop-ups
    caught close to home plate, swinging-strike contacts, etc.).
    Including them denominator-only systematically deflates the ratio
    (~40% empirical → ~16% observed). Both-sides gating matches the
    standard "among located FBs, what fraction was pulled" definition.

    Seed 3 FBs for an R batter:
      hc_x=NULL -> excluded from the ratio entirely
      hc_x=60   -> located, pulled (LF)
      hc_x=180  -> located, not pulled (oppo RF)
    Expected: pct = 1 pulled / 2 located = 0.5. The NULL-hc_x FB does
    not shift the ratio.
    """
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        rows = [
            (date(2024, 6, 2), 8820001, 1, 30.0, None, 95.0),
            (date(2024, 6, 3), 8820002, 1, 30.0, 60.0, 98.0),
            (date(2024, 6, 4), 8820003, 1, 30.0, 180.0, 97.0),
        ]
        for gd, gp, ab, la, hcx, ls in rows:
            _insert_pitch(
                s,
                batter=882001,
                game_date=gd,
                game_pk=gp,
                at_bat=ab,
                stand="R",
                launch_angle=la,
                launch_speed=ls,
                hc_x=hcx,
            )
        s.commit()

    sql = f"""
        WITH matchup_keys AS (
            SELECT 300 AS game_pk, 882001 AS batter_id, DATE '2024-06-05' AS reference_date
        ),
        batter_rolling AS (
            {rolling_features_sql()}
        )
        SELECT * FROM batter_rolling
    """
    with session_factory() as s:
        row = s.execute(text(sql)).mappings().one()

    assert row["b_pulled_fb_pct_7d"] == pytest.approx(0.5, abs=1e-6)
