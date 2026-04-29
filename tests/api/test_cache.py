"""Cache behavior integration tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest
from redis.exceptions import RedisError
from sqlalchemy import text
from src.api.dependencies import _get_session_factory
from src.core.time import current_mlb_date
from src.models.artifacts import load_model


def _flush_picks_cache() -> None:
    """Drop all `picks:today:*` keys so the test sees live DB state, not
    a stale cache from a prior run."""
    from src.core.redis_client import get_redis

    try:
        r = get_redis()
        keys = r.keys("picks:today*")
        if keys:
            r.delete(*keys)
    except Exception:  # noqa: BLE001
        pass


def _seed_prediction_for_cache_test(game_date: date, model_version: str) -> None:
    """Seed a single prediction row for cache tests."""
    sf = _get_session_factory()
    with sf() as s:
        s.execute(text("DELETE FROM predictions WHERE game_pk = 997900"))
        s.execute(text("DELETE FROM daily_schedule WHERE game_pk = 997900"))
        s.execute(
            text(
                "INSERT INTO parks (park_id, name) VALUES (99790, 'Cache Park') "
                "ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO teams (team_id, abbr, name) VALUES (9091, 'CCH', 'Cache Home') "
                "ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO teams (team_id, abbr, name) VALUES (9092, 'CCA', 'Cache Away') "
                "ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO players (mlbam_id, full_name) "
                "VALUES (790001, 'Cache Batter') ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO players (mlbam_id, full_name, throws) "
                "VALUES (790100, 'Cache Pitcher', 'R') ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO daily_schedule "
                "(game_pk, game_date, home_team_id, away_team_id, venue_id, "
                " game_start_utc, status) "
                "VALUES (997900, :d, 9091, 9092, 99790, :ts, 'Scheduled') "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "d": game_date,
                "ts": datetime(game_date.year, game_date.month, game_date.day, 23, 0, tzinfo=UTC),
            },
        )
        s.execute(
            text(
                "INSERT INTO predictions "
                "(game_pk, batter_id, pitcher_id, game_date, model_version, "
                " matchup_components, prob_at_least_one_hr, expected_hrs) "
                "VALUES (997900, 790001, 790100, :d, :mv, "
                " :mc, 0.99, 1.04) "
                "ON CONFLICT (game_pk, batter_id, model_version) DO UPDATE SET "
                "game_date = EXCLUDED.game_date, "
                "prob_at_least_one_hr = EXCLUDED.prob_at_least_one_hr, "
                "expected_hrs = EXCLUDED.expected_hrs"
            ),
            {"d": game_date, "mv": model_version, "mc": '{"starter_calibrated_prob": 0.99}'},
        )
        s.commit()


def _cleanup() -> None:
    sf = _get_session_factory()
    with sf() as s:
        s.execute(text("DELETE FROM predictions WHERE game_pk = 997900"))
        s.execute(text("DELETE FROM daily_schedule WHERE game_pk = 997900"))
        s.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_hit_on_second_identical_call(client) -> None:
    """After a first call populates cache, Redis should have a picks:today key."""
    from src.core.redis_client import get_redis

    today = current_mlb_date()
    _flush_picks_cache()
    _seed_prediction_for_cache_test(today, load_model().version)
    try:
        # First call populates cache
        r1 = await client.get("/picks/today?limit=10")
        assert r1.status_code == 200

        # Inspect Redis — should have at least one picks:today key with a TTL
        r = get_redis()
        keys = r.keys("picks:today*")
        assert len(keys) >= 1

        # The key should have a positive TTL <= 300 (5-min cache)
        ttl = r.ttl(keys[0])
        assert 0 < ttl <= 300

        # Second call returns same body (cache-hit path is graceful either way)
        r2 = await client.get("/picks/today?limit=10")
        assert r2.status_code == 200
        assert r1.json() == r2.json()
    finally:
        _flush_picks_cache()
        _cleanup()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_keys_differ_for_different_params(client) -> None:
    """Different query parameters should create different cache keys."""
    from src.core.redis_client import get_redis

    today = current_mlb_date()
    _flush_picks_cache()
    _seed_prediction_for_cache_test(today, load_model().version)
    try:
        await client.get("/picks/today?limit=10")
        await client.get("/picks/today?limit=5")
        r = get_redis()
        keys = r.keys("picks:today*")
        assert len(keys) >= 2
    finally:
        _flush_picks_cache()
        _cleanup()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_degrades_gracefully_when_redis_raises(client) -> None:
    """Force get_redis() inside cache.py to raise — endpoint must still 200."""
    today = current_mlb_date()
    _seed_prediction_for_cache_test(today, load_model().version)

    def boom(*args, **kwargs):
        raise RedisError("simulated redis down")

    try:
        with patch("src.api.cache.get_redis", side_effect=boom):
            r = await client.get("/picks/today?limit=3")
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, list)
    finally:
        _flush_picks_cache()
        _cleanup()
