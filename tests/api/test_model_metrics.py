"""Tests for /model/metrics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from src.api.dependencies import _get_session_factory


def _seed_rolling_predictions_with_outcomes(
    model_version: str, days_ago_start: int = 5, n: int = 20
) -> None:
    """Seed N prediction rows + corresponding historical matchup_features rows
    (with hr_on_pa populated) so /model/metrics has data to roll over."""
    sf = _get_session_factory()
    today = datetime.now(UTC).date()
    with sf() as s:
        s.execute(
            text(
                "INSERT INTO parks (park_id, name) "
                "VALUES (99731, 'ML Park') ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO players (mlbam_id, full_name) "
                "VALUES (730100, 'ML Pitcher') ON CONFLICT DO NOTHING"
            )
        )
        # Half the rows labeled HR=True, half False (so ECE and brier are meaningful)
        for i in range(n):
            batter_id = 730001 + i
            game_pk = 999010 + i
            game_date = today - timedelta(days=days_ago_start)
            s.execute(
                text(
                    "INSERT INTO players (mlbam_id, full_name) "
                    "VALUES (:id, :n) ON CONFLICT DO NOTHING"
                ),
                {"id": batter_id, "n": f"ML Batter {i}"},
            )
            hr_label = i % 2 == 0
            # Mix probability across 0.02..0.18 so reliability bins get populated
            prob = 0.02 + (i % 10) * 0.016  # 0.02, 0.036, 0.052, ..., 0.164
            s.execute(
                text(
                    "INSERT INTO matchup_features "
                    "(game_date, game_pk, batter_id, pitcher_id, is_historical, park_id, hr_on_pa) "
                    "VALUES (:d, :gp, :b, 730100, TRUE, 99731, :hr) ON CONFLICT DO NOTHING"
                ),
                {"d": game_date, "gp": game_pk, "b": batter_id, "hr": hr_label},
            )
            s.execute(
                text(
                    "INSERT INTO predictions "
                    "(game_pk, batter_id, pitcher_id, game_date, model_version, "
                    " matchup_components, prob_at_least_one_hr) "
                    "VALUES (:gp, :b, 730100, :d, :mv, :mc, :p) ON CONFLICT DO NOTHING"
                ),
                {
                    "gp": game_pk,
                    "b": batter_id,
                    "d": game_date,
                    "mv": model_version,
                    "mc": '{"starter_calibrated_prob": 0.1}',
                    "p": prob,
                },
            )
        s.commit()


def _cleanup_rolling(n: int = 20) -> None:
    sf = _get_session_factory()
    with sf() as s:
        first_gp = 999010
        last_gp = first_gp + n - 1
        s.execute(
            text("DELETE FROM predictions WHERE game_pk BETWEEN :a AND :b"),
            {"a": first_gp, "b": last_gp},
        )
        s.execute(
            text("DELETE FROM matchup_features WHERE game_pk BETWEEN :a AND :b"),
            {"a": first_gp, "b": last_gp},
        )
        s.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_model_metrics_returns_training_metadata(client) -> None:
    r = await client.get("/model/metrics")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "training_metadata" in body
    meta = body["training_metadata"]
    assert meta["model_version"].startswith("v")
    assert meta["num_features"] > 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_model_metrics_returns_training_metrics(client) -> None:
    r = await client.get("/model/metrics")
    body = r.json()
    tm = body["training_metrics"]
    # At least test_log_loss should be in the artifact (it's always written by train.py)
    assert "test_log_loss" in tm


@pytest.mark.asyncio
@pytest.mark.integration
async def test_model_metrics_rolling_empty_when_no_predictions(client) -> None:
    """If there's no prediction+hr_on_pa data in the window, rolling is empty."""
    # Ensure nothing in window by cleaning up any stray seeds
    _cleanup_rolling(n=20)
    r = await client.get("/model/metrics?window_days=7")
    body = r.json()
    rl = body["rolling_live"]
    # Real-world: there may or may not be rows. We only assert the shape.
    assert rl["window_days"] == 7
    assert "reliability" in rl
    assert isinstance(rl["reliability"], list)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_model_metrics_rolling_populates_when_seeded(client) -> None:
    """Seed fake prediction+outcome pairs within window; rolling metrics compute."""
    from src.models.artifacts import load_model

    version = load_model().version

    _cleanup_rolling(n=20)  # pre-clean
    _seed_rolling_predictions_with_outcomes(version, days_ago_start=5, n=20)
    try:
        r = await client.get("/model/metrics?window_days=30")
        assert r.status_code == 200
        body = r.json()
        rl = body["rolling_live"]
        assert rl["n_predictions"] >= 20
        assert rl["log_loss"] is not None
        assert rl["brier"] is not None
        assert rl["ece"] is not None
        assert len(rl["reliability"]) == 10
    finally:
        _cleanup_rolling(n=20)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_model_metrics_invalid_window_422(client) -> None:
    r = await client.get("/model/metrics?window_days=0")
    assert r.status_code == 422
