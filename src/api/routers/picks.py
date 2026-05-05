"""/picks endpoints."""

from __future__ import annotations

import logging
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.cache import cached
from src.api.dependencies import get_db, get_model
from src.api.schemas.picks import FeatureContribution, PickSummary
from src.core.time import current_mlb_date
from src.models.artifacts import LoadedModel
from src.models.odds import (
    edge_probability,
    expected_value_per_unit,
    probability_to_fair_american,
)

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/picks", tags=["picks"])


_PICKS_TODAY_SQL = text("""
    WITH latest_book_odds AS (
        SELECT
            os.*,
            ROW_NUMBER() OVER (
                PARTITION BY
                    os.game_pk,
                    os.batter_id,
                    os.market_key,
                    os.outcome_name,
                    os.bookmaker_key,
                    os.point
                ORDER BY
                    os.fetched_at DESC,
                    os.market_last_update DESC NULLS LAST,
                    os.id DESC
            ) AS rn
        FROM odds_snapshots os
        WHERE os.game_date = :target_date
          AND os.market_key = 'batter_home_runs'
          AND os.outcome_name IN ('Over', 'Yes')
          AND os.batter_id IS NOT NULL
          AND (os.point IS NULL OR ABS(os.point - 0.5) < 0.000001)
          AND COALESCE(os.raw_outcome->>'name', '') !~*
              '^\\s*[2-9][0-9]*\\+\\s+home runs?\\s*$'
    ),
    best_odds AS (
        SELECT DISTINCT ON (game_pk, batter_id)
            game_pk,
            batter_id,
            bookmaker_key,
            bookmaker_title,
            price_american,
            point,
            implied_probability,
            no_vig_probability,
            fetched_at
        FROM latest_book_odds
        WHERE rn = 1
        ORDER BY game_pk, batter_id, price_american DESC, fetched_at DESC
    )
    SELECT
        p.game_pk,
        p.game_date,
        p.batter_id,
        p.pitcher_id,
        p.prob_at_least_one_hr,
        p.expected_hrs,
        COALESCE(
            NULLIF(p.matchup_components->>'starter_raw_prob', '')::double precision,
            p.prob_at_least_one_hr
        ) AS model_rank_score,
        p.feature_contributions,
        p.model_version,
        bo.bookmaker_key AS odds_bookmaker_key,
        bo.bookmaker_title AS odds_bookmaker,
        bo.price_american AS odds_price_american,
        bo.point AS odds_point,
        bo.implied_probability AS market_implied_probability,
        bo.no_vig_probability AS market_no_vig_probability,
        bo.fetched_at AS odds_fetched_at,
        ds.game_start_utc,
        bp.full_name AS batter_name,
        bp.bats AS batter_bats,
        bp.primary_position AS batter_position,
        pp.full_name AS pitcher_name,
        pp.throws AS pitcher_throws,
        pk.name AS park_name,
        mf.b_barrel_pct_season,
        mf.b_p90_ev_season,
        mf.park_hr_factor_hand,
        mf.p_hr_per_9_season,
        mf.p_barrel_pct_allowed_season,
        mf.ctx_batting_order,
        mf.ctx_projected_pa,
        mf.wx_wind_carry_cf,
        mf.wx_temperature_f,
        mf.wx_air_density_relative,
        tm_home.abbr AS home_abbr,
        tm_away.abbr AS away_abbr,
        ds.home_team_id,
        ds.away_team_id,
        COALESCE(
            tm_batter.abbr,
            CASE
                WHEN mf.ctx_is_home IS TRUE THEN tm_home.abbr
                WHEN mf.ctx_is_home IS FALSE THEN tm_away.abbr
                ELSE NULL
            END
        ) AS team_abbr
    FROM predictions p
    LEFT JOIN daily_schedule ds ON ds.game_pk = p.game_pk
    LEFT JOIN parks pk ON pk.park_id = ds.venue_id
    LEFT JOIN players bp ON bp.mlbam_id = p.batter_id
    LEFT JOIN players pp ON pp.mlbam_id = p.pitcher_id
    LEFT JOIN LATERAL (
        SELECT pl.team_id
        FROM projected_lineups pl
        WHERE pl.game_pk = p.game_pk
          AND pl.batter_id = p.batter_id
        ORDER BY pl.is_confirmed DESC, pl.fetched_at DESC NULLS LAST, pl.batting_order ASC
        LIMIT 1
    ) batter_lineup ON TRUE
    LEFT JOIN teams tm_batter ON tm_batter.team_id = batter_lineup.team_id
    LEFT JOIN teams tm_home ON tm_home.team_id = ds.home_team_id
    LEFT JOIN teams tm_away ON tm_away.team_id = ds.away_team_id
    LEFT JOIN matchup_features mf
      ON mf.game_pk = p.game_pk
     AND mf.batter_id = p.batter_id
     AND mf.pitcher_id = p.pitcher_id
     AND mf.game_date = p.game_date
    LEFT JOIN best_odds bo
      ON bo.game_pk = p.game_pk
     AND bo.batter_id = p.batter_id
    WHERE p.game_date = :target_date
      AND p.model_version = :model_version
      AND p.prob_at_least_one_hr >= :min_prob
      AND (CAST(:team AS text) IS NULL
           OR COALESCE(
                tm_batter.abbr,
                CASE
                    WHEN mf.ctx_is_home IS TRUE THEN tm_home.abbr
                    WHEN mf.ctx_is_home IS FALSE THEN tm_away.abbr
                    ELSE NULL
                END
           ) = UPPER(CAST(:team AS text)))
    ORDER BY
        CASE CAST(:sort AS text)
             WHEN 'expected_hrs' THEN p.expected_hrs
             ELSE p.prob_at_least_one_hr
         END DESC NULLS LAST,
        p.prob_at_least_one_hr DESC NULLS LAST,
        COALESCE(
            NULLIF(p.matchup_components->>'starter_raw_prob', '')::double precision,
            p.prob_at_least_one_hr
        ) DESC NULLS LAST,
        mf.ctx_projected_pa DESC NULLS LAST,
        mf.ctx_batting_order ASC NULLS LAST,
        p.batter_id ASC
    LIMIT :limit
    """)


def _row_to_pick(row) -> PickSummary:
    contribs_raw = row["feature_contributions"] or {}
    # Top model drivers by absolute contribution.
    sorted_items = sorted(contribs_raw.items(), key=lambda kv: -abs(kv[1]))[:5]
    contributions = [FeatureContribution(name=k, contribution=float(v)) for k, v in sorted_items]

    def _f(key: str) -> float | None:
        v = row.get(key) if hasattr(row, "get") else row[key]
        return float(v) if v is not None else None

    market_p = _f("market_implied_probability")
    model_p = float(row["prob_at_least_one_hr"])
    odds_price = row["odds_price_american"]
    fair_odds = probability_to_fair_american(model_p) if 0.0 < model_p < 1.0 else None
    model_edge = (
        edge_probability(model_probability=model_p, market_probability=market_p)
        if market_p
        else None
    )
    ev = (
        expected_value_per_unit(model_probability=model_p, american_odds=int(odds_price))
        if odds_price is not None
        else None
    )

    return PickSummary(
        batter_id=int(row["batter_id"]),
        batter_name=row["batter_name"],
        batter_bats=row["batter_bats"],
        batter_position=row["batter_position"],
        team_abbr=row["team_abbr"],
        game_pk=int(row["game_pk"]),
        game_date=row["game_date"],
        game_start_utc=row["game_start_utc"],
        park_name=row["park_name"],
        home_team_abbr=row["home_abbr"],
        away_team_abbr=row["away_abbr"],
        pitcher_id=int(row["pitcher_id"]),
        pitcher_name=row["pitcher_name"],
        pitcher_throws=row["pitcher_throws"],
        prob_at_least_one_hr=model_p,
        expected_hrs=(float(row["expected_hrs"]) if row["expected_hrs"] is not None else None),
        model_rank_score=_f("model_rank_score"),
        odds_bookmaker=row["odds_bookmaker"],
        odds_bookmaker_key=row["odds_bookmaker_key"],
        odds_price_american=(int(odds_price) if odds_price is not None else None),
        odds_point=_f("odds_point"),
        market_implied_probability=market_p,
        market_no_vig_probability=_f("market_no_vig_probability"),
        fair_odds_american=fair_odds,
        model_edge=model_edge,
        expected_value_per_unit=ev,
        odds_fetched_at=row["odds_fetched_at"],
        barrel_pct_season=_f("b_barrel_pct_season"),
        p90_ev_season=_f("b_p90_ev_season"),
        park_hr_factor_hand=_f("park_hr_factor_hand"),
        pitcher_hr_per_9_season=_f("p_hr_per_9_season"),
        pitcher_barrel_pct_allowed_season=_f("p_barrel_pct_allowed_season"),
        batting_order=(
            int(row["ctx_batting_order"]) if row["ctx_batting_order"] is not None else None
        ),
        projected_pas=_f("ctx_projected_pa"),
        wind_carry_cf=_f("wx_wind_carry_cf"),
        temperature_f=_f("wx_temperature_f"),
        air_density_relative=_f("wx_air_density_relative"),
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
    model_version: str,
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
                "model_version": model_version,
            },
        )
        .mappings()
        .all()
    )
    return [_row_to_pick(r) for r in rows]


_LATEST_DATE_SQL = text(
    "SELECT MAX(game_date) FROM predictions WHERE model_version = :model_version"
)


@router.get("/today", response_model=list[PickSummary])
async def picks_today(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    loaded: Annotated[LoadedModel, Depends(get_model)],
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

    If today has no predictions yet (daily inference not yet run, or the
    pipeline is a day behind a calendar rollover), the endpoint falls
    back to the most recent date that does. Clients get real picks
    instead of an empty slate; the `game_date` field on each pick makes
    the staleness visible.
    """
    target_date = current_mlb_date()
    picks = await _picks_today_cached(
        target_date=target_date,
        limit=limit,
        min_prob=min_prob,
        team=team,
        sort=sort,
        model_version=loaded.version,
        request=request,
        db=db,
    )
    if picks:
        return picks

    latest = db.execute(_LATEST_DATE_SQL, {"model_version": loaded.version}).scalar()
    if latest is None or latest == target_date:
        return picks  # truly empty — no predictions anywhere
    _log.info(
        "picks_today falling back to most recent date",
        extra={"today": target_date.isoformat(), "served": latest.isoformat()},
    )
    return await _picks_today_cached(
        target_date=latest,
        limit=limit,
        min_prob=min_prob,
        team=team,
        sort=sort,
        model_version=loaded.version,
        request=request,
        db=db,
    )
