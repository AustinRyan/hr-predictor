"""Daily schedule + lineup + probable-pitcher orchestrator.

Pulls a single date's games from MLB StatsAPI (schedule with probable
pitchers hydrated), then for each game pulls the live boxscore to
collect the batting order, and the feed/live payload to detect roof
status. Upserts into `daily_schedule` and `projected_lineups`.

Idempotency: all writes use ``ON CONFLICT DO UPDATE``. Doubleheaders
handled -- ``game_pk`` is the natural key. Rainouts/postponements update
``status`` but never delete rows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.db import get_engine
from src.core.models import DailySchedule, ProjectedLineup
from src.ingestion.mlb_statsapi_client import (
    fetch_boxscore,
    fetch_game_content,
    fetch_schedule_with_probables,
)
from src.ingestion.wire_models import ScheduleGameWithProbables

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class DailyScheduleResult:
    target_date: date
    games_upserted: int
    lineups_upserted: int


def persist_daily_schedule(target_date: date, *, engine: Engine | None = None) -> int:
    """Fetch + upsert one date's games. Returns count of games written."""
    engine = engine or get_engine()
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    games = list(fetch_schedule_with_probables(target_date, target_date))
    if not games:
        _log.info("no games scheduled", extra={"date": target_date.isoformat()})
        return 0

    schedule_rows: list[dict[str, Any]] = []
    lineup_rows: list[dict[str, Any]] = []

    for g in games:
        roof_status = _safe_fetch_roof(g)
        schedule_rows.append(_schedule_row(g, roof_status))
        lineup_rows.extend(_lineup_rows_for_game(g))

    with session_factory() as session:
        _upsert_schedule(session, schedule_rows)
        _upsert_lineups(session, lineup_rows)
        session.commit()

    _log.info(
        "daily schedule persisted",
        extra={
            "date": target_date.isoformat(),
            "games": len(schedule_rows),
            "lineups": len(lineup_rows),
        },
    )
    return len(schedule_rows)


def _safe_fetch_roof(g: ScheduleGameWithProbables) -> str | None:
    try:
        return fetch_game_content(g.game_pk)
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "roof status fetch failed, storing null",
            extra={"game_pk": g.game_pk, "err": str(exc)},
        )
        return None


def _schedule_row(g: ScheduleGameWithProbables, roof_status: str | None) -> dict[str, Any]:
    official = g.official_date or g.game_date.date()
    detailed = None
    if g.status is not None:
        detailed = g.status.detailed_state or g.status.abstract_game_state

    return {
        "game_pk": g.game_pk,
        "game_date": official,
        "home_team_id": g.home_team_id,
        "away_team_id": g.away_team_id,
        "venue_id": g.venue_id,
        "game_start_utc": g.game_date,
        "game_start_local": None,  # populated only when venue tz known; skip for now
        "probable_home_pitcher_id": g.home_probable_pitcher_id,
        "probable_away_pitcher_id": g.away_probable_pitcher_id,
        "status": (detailed or "Scheduled")[:32],
        "roof_status": roof_status,
        "fetched_at": datetime.now(UTC),
    }


def _lineup_rows_for_game(g: ScheduleGameWithProbables) -> list[dict[str, Any]]:
    """Pull batting order from boxscore. Empty if lineup not yet posted."""
    try:
        bx = fetch_boxscore(g.game_pk)
    except Exception as exc:  # noqa: BLE001
        _log.warning("boxscore fetch failed", extra={"game_pk": g.game_pk, "err": str(exc)})
        return []

    rows: list[dict[str, Any]] = []
    for side_obj in (bx.teams.home, bx.teams.away):
        team_id = side_obj.team.id
        if team_id is None:
            continue
        for slot, batter_id in enumerate(side_obj.batting_order, start=1):
            rows.append(
                {
                    "game_pk": g.game_pk,
                    "team_id": team_id,
                    "batter_id": batter_id,
                    "batting_order": slot,
                    "is_confirmed": False,  # boxscore doesn't disambiguate; set True only when finals-known
                    "fetched_at": datetime.now(UTC),
                }
            )
    return rows


def _upsert_schedule(session: Session, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    stmt = pg_insert(DailySchedule).values(rows)
    update_cols = {
        c.name: getattr(stmt.excluded, c.name)
        for c in DailySchedule.__table__.columns
        if c.name not in {"game_pk"}
    }
    stmt = stmt.on_conflict_do_update(index_elements=[DailySchedule.game_pk], set_=update_cols)
    session.execute(stmt)
    return len(rows)


def _upsert_lineups(session: Session, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    stmt = pg_insert(ProjectedLineup).values(rows)
    update_cols = {
        "batter_id": stmt.excluded.batter_id,
        "is_confirmed": stmt.excluded.is_confirmed,
        "fetched_at": stmt.excluded.fetched_at,
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            ProjectedLineup.game_pk,
            ProjectedLineup.team_id,
            ProjectedLineup.batting_order,
        ],
        set_=update_cols,
    )
    session.execute(stmt)
    return len(rows)
