"""Unit + integration tests for Phase 3 context features."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from src.features.context import (
    PA_BY_BATTING_ORDER,
    day_night_letter,
    days_since_last_game,
    projected_pa_for_slot,
    same_hand,
)


def test_pa_map_covers_slots_1_to_9() -> None:
    assert set(PA_BY_BATTING_ORDER.keys()) == set(range(1, 10))


def test_projected_pa_for_slot_9_is_3_75() -> None:
    assert projected_pa_for_slot(9) == pytest.approx(3.75)


def test_projected_pa_for_slot_1_is_4_60() -> None:
    assert projected_pa_for_slot(1) == pytest.approx(4.60)


def test_projected_pa_for_slot_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        projected_pa_for_slot(0)
    with pytest.raises(ValueError):
        projected_pa_for_slot(10)
    with pytest.raises(ValueError):
        projected_pa_for_slot(-1)


def test_same_hand_pairs() -> None:
    # Same-handed matchup: True
    assert same_hand("L", "L") is True
    assert same_hand("R", "R") is True
    # Opposite: False
    assert same_hand("L", "R") is False
    assert same_hand("R", "L") is False
    # Switch-hitter: always False (treat as never same-handed)
    assert same_hand("S", "L") is False
    assert same_hand("S", "R") is False
    # Unknown batter stand: None → False by convention
    assert same_hand(None, "R") is False
    assert same_hand("R", None) is False


def test_day_night_letter_from_game_start_utc() -> None:
    # 19:00 UTC = 3pm ET = day game
    assert day_night_letter(datetime(2024, 7, 4, 19, 0, tzinfo=UTC)) == "D"
    # 01:00 UTC = 9pm ET = night game
    assert day_night_letter(datetime(2024, 7, 5, 1, 0, tzinfo=UTC)) == "N"
    # 23:00 UTC = 7pm ET = night (cutoff at 21 UTC / 5pm ET)
    assert day_night_letter(datetime(2024, 7, 4, 23, 0, tzinfo=UTC)) == "N"
    # 20:00 UTC = 4pm ET = day (just under cutoff)
    assert day_night_letter(datetime(2024, 7, 4, 20, 0, tzinfo=UTC)) == "D"


def test_day_night_letter_naive_datetime_treated_as_utc() -> None:
    """Defensive: some DB rows may arrive tz-naive. Treat as UTC."""
    assert day_night_letter(datetime(2024, 7, 4, 19, 0)) == "D"
    assert day_night_letter(datetime(2024, 7, 5, 1, 0)) == "N"


@pytest.mark.integration
def test_days_since_last_game_returns_delta(test_engine: Engine, clean_tables) -> None:
    """Seed a batter with pitches on two dates, query days-rest for a third."""
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        # Seed minimal park + 1 game on 2024-06-01 and 1 on 2024-06-08.
        s.execute(
            text("INSERT INTO parks (park_id, name) VALUES (99801, 'tp') " "ON CONFLICT DO NOTHING")
        )
        for game_date, game_pk in [
            (date(2024, 6, 1), 888801),
            (date(2024, 6, 8), 888802),
        ]:
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher) "
                    "VALUES (:d, :g, 1, 1, 555501, 555502)"
                ),
                {"d": game_date, "g": game_pk},
            )
        s.commit()

        # Days since last game for batter 555501 relative to 2024-06-15: last game was 2024-06-08 → 7 days.
        result = days_since_last_game(555501, date(2024, 6, 15), s)
        assert result == 7

        # Pitcher 555502 relative to 2024-06-02: last game was 2024-06-01 → 1 day.
        assert days_since_last_game(555502, date(2024, 6, 2), s) == 1


@pytest.mark.integration
def test_days_since_last_game_returns_none_for_unknown_player(
    test_engine: Engine, clean_tables
) -> None:
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        # No seeded pitches for player 9999999.
        assert days_since_last_game(9999999, date(2024, 7, 1), s) is None


@pytest.mark.integration
def test_days_since_last_game_strict_prior(test_engine: Engine, clean_tables) -> None:
    """Games on the reference date itself do NOT count (leakage guard)."""
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text(
                "INSERT INTO parks (park_id, name) VALUES (99802, 'tp2') " "ON CONFLICT DO NOTHING"
            )
        )
        # Game on the reference date itself.
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher) "
                "VALUES ('2024-07-04', 888803, 1, 1, 555503, 555504)"
            )
        )
        # Prior game.
        s.execute(
            text(
                "INSERT INTO statcast_pitches "
                "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher) "
                "VALUES ('2024-06-30', 888804, 1, 1, 555503, 555504)"
            )
        )
        s.commit()

        # Reference = 2024-07-04; prior game was 2024-06-30. Delta = 4 days.
        assert days_since_last_game(555503, date(2024, 7, 4), s) == 4


@pytest.mark.integration
def test_batting_order_backfill_infers_slots(test_engine: Engine, clean_tables) -> None:
    """Seed 3 pitches for 3 distinct batters on a single team-side
    (inning_topbot='Top') with distinct at_bat_numbers, verify the
    backfill script assigns slots 1/2/3 in first-PA order."""
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text("INSERT INTO parks (park_id, name) VALUES (99701, 'tp') ON CONFLICT DO NOTHING")
        )
        # Seed 3 batters across 3 at-bats in a single game.
        for ab_num, batter_id in [(1, 997001), (2, 997002), (3, 997003)]:
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, "
                    " inning_topbot, events, stand) "
                    "VALUES ('2024-06-01', 9970001, :ab, 1, :b, 997100, 'Top', 'single', 'R')"
                ),
                {"ab": ab_num, "b": batter_id},
            )
        # Seed matching matchup_features rows.
        for batter_id in [997001, 997002, 997003]:
            s.execute(
                text(
                    "INSERT INTO matchup_features "
                    "(game_date, game_pk, batter_id, pitcher_id, is_historical, park_id) "
                    "VALUES ('2024-06-01', 9970001, :b, 997100, TRUE, 99701)"
                ),
                {"b": batter_id},
            )
        s.commit()

    # Replicate the UPDATE in-test to avoid harness plumbing (script uses prod engine).
    from phases.phase3.batting_order_backfill import _pa_case_sql, _tto_case_sql

    with session_factory() as s:
        s.execute(text(f"""
            WITH per_batter_first_ab AS (
                SELECT sp.game_pk, sp.inning_topbot, sp.batter, MIN(sp.at_bat_number) AS first_ab
                FROM statcast_pitches sp
                WHERE sp.inning_topbot IS NOT NULL
                GROUP BY sp.game_pk, sp.inning_topbot, sp.batter
            ),
            ranked AS (
                SELECT pb.game_pk, pb.batter AS batter_id,
                       ROW_NUMBER() OVER (PARTITION BY pb.game_pk, pb.inning_topbot ORDER BY pb.first_ab)::int AS slot
                FROM per_batter_first_ab pb
            )
            UPDATE matchup_features mf
            SET ctx_batting_order = r.slot,
                ctx_projected_pa = {_pa_case_sql()},
                p_tto_penalty = {_tto_case_sql()}
            FROM ranked r
            WHERE mf.game_pk = r.game_pk AND mf.batter_id = r.batter_id
              AND mf.is_historical AND r.slot <= 9
        """))
        s.commit()
        rows = (
            s.execute(
                text(
                    "SELECT batter_id, ctx_batting_order, ctx_projected_pa, p_tto_penalty "
                    "FROM matchup_features WHERE game_pk = 9970001 ORDER BY batter_id"
                )
            )
            .mappings()
            .all()
        )

    # Batters were inserted in at-bat order 1/2/3 -> slots 1/2/3.
    assert rows[0]["ctx_batting_order"] == 1
    assert rows[1]["ctx_batting_order"] == 2
    assert rows[2]["ctx_batting_order"] == 3
    assert rows[0]["ctx_projected_pa"] == pytest.approx(4.60, abs=0.001)
    assert rows[2]["ctx_projected_pa"] == pytest.approx(4.40, abs=0.001)
    # p_tto_penalty is the same ~1.083 for all slots 1-9 (first 3 PAs
    # dominate the weighted average, PA 4+ is bullpen).
    assert rows[0]["p_tto_penalty"] == pytest.approx(1.0833, abs=0.005)
