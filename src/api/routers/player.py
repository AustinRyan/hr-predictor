"""/player endpoints."""

from __future__ import annotations

import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.cache import cached
from src.api.dependencies import get_db, get_model
from src.api.schemas.player import (
    PlayerDetail,
    PlayerProfile,
    PlayerRollingStats,
    PlayerTodayPrediction,
)
from src.core.time import current_mlb_date
from src.models.artifacts import LoadedModel

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/player", tags=["player"])


_PROFILE_SQL = text("""
    SELECT mlbam_id, full_name, first_name, last_name,
           bats, throws, primary_position, active
    FROM players
    WHERE mlbam_id = :mlbam_id
    """)

_ROLLING_SQL = text("""
    SELECT game_date AS as_of,
           b_barrel_pct_30d, b_hardhit_pct_30d, b_avg_ev_30d, b_p90_ev_30d,
           b_avg_la_30d, b_pulled_fb_pct_30d, b_xwobacon_30d,
           b_hr_per_pa_30d, b_pa_count_30d,
           b_barrel_pct_season, b_hr_per_pa_season, b_pa_count_season
    FROM matchup_features
    WHERE batter_id = :mlbam_id AND is_historical
    ORDER BY game_date DESC
    LIMIT 1
    """)

_TODAY_PRED_SQL = text("""
    SELECT game_pk, pitcher_id, prob_at_least_one_hr,
           expected_hrs, projected_pas, model_version
    FROM predictions
    WHERE batter_id = :mlbam_id
      AND game_date = :today
      AND model_version = :model_version
    ORDER BY prob_at_least_one_hr DESC
    LIMIT 1
    """)


@cached(
    ttl_seconds=3600,  # 1 hour
    key_prefix="player:detail",
    model=PlayerDetail,
)
async def _player_detail_cached(
    mlbam_id: int,
    today: date,
    model_version: str,
    db: Session,
    request: Request,  # for cache-key model-version namespacing
) -> PlayerDetail:
    profile_row = db.execute(_PROFILE_SQL, {"mlbam_id": mlbam_id}).mappings().first()
    if profile_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"player {mlbam_id} not found",
        )

    profile = PlayerProfile(**dict(profile_row))

    rolling_row = db.execute(_ROLLING_SQL, {"mlbam_id": mlbam_id}).mappings().first()
    if rolling_row is None:
        rolling = PlayerRollingStats(as_of=None)
    else:
        rolling = PlayerRollingStats(**dict(rolling_row))

    today_row = (
        db.execute(
            _TODAY_PRED_SQL,
            {"mlbam_id": mlbam_id, "today": today, "model_version": model_version},
        )
        .mappings()
        .first()
    )
    today_prediction: PlayerTodayPrediction | None = (
        PlayerTodayPrediction(**dict(today_row)) if today_row else None
    )

    return PlayerDetail(
        profile=profile,
        rolling=rolling,
        today_prediction=today_prediction,
    )


@router.get("/{mlbam_id}", response_model=PlayerDetail)
async def player_detail(
    mlbam_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    loaded: Annotated[LoadedModel, Depends(get_model)],
) -> PlayerDetail:
    """Return player profile + recent rolling features + today's prediction."""
    today = current_mlb_date()
    return await _player_detail_cached(
        mlbam_id=mlbam_id,
        today=today,
        model_version=loaded.version,
        db=db,
        request=request,
    )
