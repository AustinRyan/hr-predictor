"""Tests for /picks endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from src.api.dependencies import _get_session_factory
from src.core.redis_client import get_redis


def _flush_picks_cache() -> None:
    """Drop all `picks:today:*` keys so the test sees live DB state, not
    a stale cache from a prior run."""
    try:
        r = get_redis()
        keys = r.keys("picks:today*")
        if keys:
            r.delete(*keys)
    except Exception:  # noqa: BLE001
        # Redis unreachable: endpoint degrades to direct-DB, tests still valid
        pass


def _seed_predictions(game_date: date) -> None:
    """Seed 5 prediction rows against the live dev DB."""
    _flush_picks_cache()
    sf = _get_session_factory()
    with sf() as s:
        # Clean any pre-existing rows for this date
        s.execute(text("DELETE FROM predictions WHERE game_date = :d"), {"d": game_date})
        # Park + schedule for FK context
        s.execute(
            text(
                "INSERT INTO parks (park_id, name) VALUES (99701, 'Test Park') "
                "ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO teams (team_id, abbr, name) VALUES (9001, 'TST', 'Test Home') "
                "ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO teams (team_id, abbr, name) VALUES (9002, 'VIS', 'Test Away') "
                "ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO daily_schedule "
                "(game_pk, game_date, home_team_id, away_team_id, venue_id, "
                " game_start_utc, status) "
                "VALUES (997001, :d, 9001, 9002, 99701, :ts, 'Scheduled') "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "d": game_date,
                "ts": datetime(game_date.year, game_date.month, game_date.day, 23, 0, tzinfo=UTC),
            },
        )
        # Players
        for pid, name in [
            (700001, "Test Batter A"),
            (700002, "Test Batter B"),
            (700003, "Test Batter C"),
            (700004, "Test Batter D"),
            (700005, "Test Batter E"),
            (700100, "Test Pitcher"),
        ]:
            s.execute(
                text(
                    "INSERT INTO players (mlbam_id, full_name, throws) "
                    "VALUES (:id, :n, 'R') ON CONFLICT DO NOTHING"
                ),
                {"id": pid, "n": name},
            )
        # 5 predictions with descending prob
        for i, pid in enumerate([700001, 700002, 700003, 700004, 700005]):
            s.execute(
                text(
                    "INSERT INTO predictions "
                    "(game_pk, batter_id, pitcher_id, game_date, model_version, "
                    " matchup_components, projected_pas, prob_at_least_one_hr, "
                    " prob_at_least_two_hr, expected_hrs, feature_contributions) "
                    "VALUES (997001, :b, 700100, :d, 'v20260423_173917', "
                    " :mc, 4.29, :prob, 0.01, :eh, :fc)"
                ),
                {
                    "b": pid,
                    "d": game_date,
                    "mc": '{"starter_raw_prob": 0.2, "starter_calibrated_prob": 0.2}',
                    "prob": 0.20 - i * 0.03,
                    "eh": 0.25 - i * 0.03,
                    "fc": (
                        '{"b_barrel_pct_season": 0.05, '
                        '"park_hr_factor_hand": 0.03, '
                        '"b_p90_ev_season": 0.02, '
                        '"wx_wind_carry_cf": 0.01}'
                    ),
                },
            )
        s.commit()


def _cleanup_predictions(game_date: date) -> None:
    sf = _get_session_factory()
    with sf() as s:
        s.execute(text("DELETE FROM predictions WHERE game_date = :d"), {"d": game_date})
        s.execute(text("DELETE FROM daily_schedule WHERE game_pk = 997001"))
        s.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_picks_today_returns_sorted_by_prob(client) -> None:
    today = datetime.now(UTC).date()
    _seed_predictions(today)
    try:
        r = await client.get("/picks/today")
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) >= 5
        # Top-5 we seeded are the highest-prob ones (0.20 down to 0.08)
        top5 = [row for row in body if row["batter_id"] in (700001, 700002, 700003, 700004, 700005)]
        assert len(top5) == 5
        probs = [row["prob_at_least_one_hr"] for row in top5]
        assert probs == sorted(probs, reverse=True)
        # Enrichment
        first = top5[0]
        assert first["batter_name"] == "Test Batter A"
        assert first["pitcher_name"] == "Test Pitcher"
        assert first["pitcher_throws"] == "R"
        assert first["park_name"] == "Test Park"
        assert first["model_version"] == "v20260423_173917"
        assert len(first["top_contributing_features"]) == 3
    finally:
        _cleanup_predictions(today)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_picks_today_respects_limit(client) -> None:
    today = datetime.now(UTC).date()
    _seed_predictions(today)
    try:
        r = await client.get("/picks/today?limit=2")
        assert r.status_code == 200
        # Seeded 5; limit 2 → at most 2 for OUR seeds (other real rows may be
        # present; filter by id)
        body = r.json()
        our_rows = [b for b in body if b["batter_id"] in (700001, 700002, 700003, 700004, 700005)]
        assert len(our_rows) <= 2
    finally:
        _cleanup_predictions(today)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_picks_today_min_prob_filter(client) -> None:
    today = datetime.now(UTC).date()
    _seed_predictions(today)
    try:
        r = await client.get("/picks/today?min_prob=0.15")
        assert r.status_code == 200
        body = r.json()
        for row in body:
            assert row["prob_at_least_one_hr"] >= 0.15
    finally:
        _cleanup_predictions(today)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_picks_today_team_filter(client) -> None:
    today = datetime.now(UTC).date()
    _seed_predictions(today)
    try:
        r = await client.get("/picks/today?team=TST")
        assert r.status_code == 200
        body = r.json()
        # Our seeded game has home team TST; should return our 5 seeds at minimum.
        our_rows = [b for b in body if b["batter_id"] in (700001, 700002, 700003, 700004, 700005)]
        assert len(our_rows) == 5
    finally:
        _cleanup_predictions(today)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_picks_today_invalid_limit_returns_422(client) -> None:
    _flush_picks_cache()
    r = await client.get("/picks/today?limit=0")
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error"
