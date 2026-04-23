"""/picks endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.cache import cached
from src.api.dependencies import get_db
from src.api.schemas.picks import FeatureContribution, PickSummary

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/picks", tags=["picks"])


_PICKS_TODAY_SQL = text("""
    SELECT
        p.game_pk,
        p.game_date,
        p.batter_id,
        p.pitcher_id,
        p.prob_at_least_one_hr,
        p.expected_hrs,
        p.feature_contributions,
        p.model_version,
        ds.game_start_utc,
        bp.full_name AS batter_name,
        pp.full_name AS pitcher_name,
        pp.throws AS pitcher_throws,
        pk.name AS park_name,
        tm_home.abbr AS home_abbr,
        tm_away.abbr AS away_abbr,
        ds.home_team_id,
        ds.away_team_id,
        -- batter's team side inferred later in Python via lineup; for now NULL
        NULL::text AS team_abbr
    FROM predictions p
    LEFT JOIN daily_schedule ds ON ds.game_pk = p.game_pk
    LEFT JOIN parks pk ON pk.park_id = ds.venue_id
    LEFT JOIN players bp ON bp.mlbam_id = p.batter_id
    LEFT JOIN players pp ON pp.mlbam_id = p.pitcher_id
    LEFT JOIN teams tm_home ON tm_home.team_id = ds.home_team_id
    LEFT JOIN teams tm_away ON tm_away.team_id = ds.away_team_id
    WHERE p.game_date = :target_date
      AND p.prob_at_least_one_hr >= :min_prob
      AND (CAST(:team AS text) IS NULL
           OR tm_home.abbr = CAST(:team AS text)
           OR tm_away.abbr = CAST(:team AS text))
    ORDER BY
        CASE CAST(:sort AS text)
             WHEN 'expected_hrs' THEN p.expected_hrs
             ELSE p.prob_at_least_one_hr
         END DESC NULLS LAST,
        p.prob_at_least_one_hr DESC NULLS LAST
    LIMIT :limit
    """)


def _row_to_pick(row) -> PickSummary:
    contribs_raw = row["feature_contributions"] or {}
    # Top-3 by absolute contribution
    sorted_items = sorted(contribs_raw.items(), key=lambda kv: -abs(kv[1]))[:3]
    contributions = [FeatureContribution(name=k, contribution=float(v)) for k, v in sorted_items]

    # Team abbreviation: we don't have a projected_lineups join here; expose as None
    # in v1. Phase 7+ can wire it in if UI needs it.
    team_abbr = None

    return PickSummary(
        batter_id=int(row["batter_id"]),
        batter_name=row["batter_name"],
        team_abbr=team_abbr,
        game_pk=int(row["game_pk"]),
        game_date=row["game_date"],
        game_start_utc=row["game_start_utc"],
        park_name=row["park_name"],
        pitcher_id=int(row["pitcher_id"]),
        pitcher_name=row["pitcher_name"],
        pitcher_throws=row["pitcher_throws"],
        prob_at_least_one_hr=float(row["prob_at_least_one_hr"]),
        expected_hrs=(float(row["expected_hrs"]) if row["expected_hrs"] is not None else None),
        top_contributing_features=contributions,
        model_version=row["model_version"],
    )


@cached(
    ttl_seconds=300,
    key_prefix="picks:today",
    model=PickSummary,
    model_list=True,
)
def _picks_today_cached(
    target_date: date,
    limit: int,
    min_prob: float,
    team: str | None,
    sort: str,
    request: Request,
    db: Session,
) -> list[PickSummary]:
    rows = (
        db.execute(
            _PICKS_TODAY_SQL,
            {
                "target_date": target_date,
                "limit": limit,
                "min_prob": min_prob,
                "team": team,
                "sort": sort,
            },
        )
        .mappings()
        .all()
    )
    return [_row_to_pick(r) for r in rows]


@router.get("/today", response_model=list[PickSummary])
async def picks_today(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    min_prob: Annotated[float, Query(ge=0.0, le=1.0)] = 0.0,
    team: Annotated[str | None, Query(max_length=4)] = None,
    sort: Annotated[Literal["prob", "expected_hrs"], Query()] = "prob",
) -> list[PickSummary]:
    """Return today's ranked picks.

    - `limit`: max rows (1-200, default 20)
    - `min_prob`: filter below this P(>=1 HR); 0 for no filter
    - `team`: restrict to a team abbreviation (home OR away)
    - `sort`: rank by `prob` (default) or `expected_hrs`
    """
    target_date = datetime.now(UTC).date()
    return await _picks_today_cached(
        target_date=target_date,
        limit=limit,
        min_prob=min_prob,
        team=team,
        sort=sort,
        request=request,
        db=db,
    )
