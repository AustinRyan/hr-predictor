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

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.db import get_engine
from src.core.models import DailySchedule, Player, ProjectedLineup
from src.ingestion.mlb_statsapi_client import (
    fetch_boxscore,
    fetch_game_content,
    fetch_schedule_with_probables,
)
from src.ingestion.wire_models import BoxscoreTeamSide, ScheduleGameWithProbables

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class DailyScheduleResult:
    target_date: date
    games_upserted: int
    lineups_upserted: int


@dataclass(slots=True)
class BoxscoreRows:
    lineups: list[dict[str, Any]]
    players: list[dict[str, Any]]


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
    player_rows: list[dict[str, Any]] = []

    for g in games:
        roof_status = _safe_fetch_roof(g)
        schedule_rows.append(_schedule_row(g, roof_status))
        player_rows.extend(_probable_pitcher_rows(g))
        boxscore_rows = _boxscore_rows_for_game(g)
        lineup_rows.extend(boxscore_rows.lineups)
        player_rows.extend(boxscore_rows.players)

    with session_factory() as session:
        _upsert_schedule(session, schedule_rows)
        _upsert_players(session, player_rows)
        _upsert_lineups(session, lineup_rows)
        session.commit()

    _log.info(
        "daily schedule persisted",
        extra={
            "date": target_date.isoformat(),
            "games": len(schedule_rows),
            "lineups": len(lineup_rows),
            "players": len(_dedupe_player_rows(player_rows)),
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


def _boxscore_rows_for_game(g: ScheduleGameWithProbables) -> BoxscoreRows:
    """Pull batting order + player bio refs from boxscore."""
    try:
        bx = fetch_boxscore(g.game_pk)
    except Exception as exc:  # noqa: BLE001
        _log.warning("boxscore fetch failed", extra={"game_pk": g.game_pk, "err": str(exc)})
        return BoxscoreRows(lineups=[], players=[])

    lineup_rows: list[dict[str, Any]] = []
    player_rows: list[dict[str, Any]] = []
    fetched_at = datetime.now(UTC)
    for side_obj in (bx.teams.home, bx.teams.away):
        team_id = side_obj.team.id
        if team_id is not None:
            for slot, batter_id in enumerate(side_obj.batting_order, start=1):
                lineup_rows.append(
                    {
                        "game_pk": g.game_pk,
                        "team_id": team_id,
                        "batter_id": batter_id,
                        "batting_order": slot,
                        # Boxscore doesn't disambiguate; set True only when finals-known.
                        "is_confirmed": False,
                        "fetched_at": fetched_at,
                    }
                )
        player_rows.extend(_player_rows_from_boxscore_side(side_obj))
    return BoxscoreRows(lineups=lineup_rows, players=player_rows)


def _lineup_rows_for_game(g: ScheduleGameWithProbables) -> list[dict[str, Any]]:
    """Pull batting order from boxscore. Empty if lineup not yet posted."""
    return _boxscore_rows_for_game(g).lineups


def _probable_pitcher_rows(g: ScheduleGameWithProbables) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for side in (g.teams.home if g.teams else None, g.teams.away if g.teams else None):
        pitcher = side.probable_pitcher if side is not None else None
        if pitcher is None:
            continue
        row = _player_row(mlbam_id=pitcher.id, full_name=pitcher.full_name)
        if row is not None:
            rows.append(row)
    return rows


def _player_rows_from_boxscore_side(side: BoxscoreTeamSide) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for player in side.players.values():
        row = _player_row(
            mlbam_id=player.mlbam_id,
            full_name=player.full_name,
            bats=player.bats,
            throws=player.throws,
            primary_position=player.primary_position,
        )
        if row is not None:
            rows.append(row)
    return rows


def _player_row(
    *,
    mlbam_id: int | None,
    full_name: str | None = None,
    bats: str | None = None,
    throws: str | None = None,
    primary_position: str | None = None,
) -> dict[str, Any] | None:
    if mlbam_id is None:
        return None
    clean_name = _clean_text(full_name, max_len=128)
    first_name, last_name = _split_name(clean_name)
    return {
        "mlbam_id": int(mlbam_id),
        "full_name": clean_name,
        "first_name": first_name,
        "last_name": last_name,
        "bats": _clean_code(bats, max_len=1),
        "throws": _clean_code(throws, max_len=1),
        "primary_position": _clean_code(primary_position, max_len=4),
        "active": True,
    }


def _clean_text(value: str | None, *, max_len: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned[:max_len] or None


def _clean_code(value: str | None, *, max_len: int) -> str | None:
    cleaned = _clean_text(value, max_len=max_len)
    return cleaned.upper() if cleaned is not None else None


def _split_name(full_name: str | None) -> tuple[str | None, str | None]:
    if full_name is None:
        return None, None
    parts = full_name.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


def _dedupe_player_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[int, dict[str, Any]] = {}
    for row in rows:
        mlbam_id = int(row["mlbam_id"])
        current = deduped.setdefault(
            mlbam_id,
            {
                "mlbam_id": mlbam_id,
                "full_name": None,
                "first_name": None,
                "last_name": None,
                "bats": None,
                "throws": None,
                "primary_position": None,
                "active": True,
            },
        )
        for key, value in row.items():
            if value is not None and value != "":
                current[key] = value
    return list(deduped.values())


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


def _upsert_players(session: Session, rows: list[dict[str, Any]]) -> int:
    deduped_rows = _dedupe_player_rows(rows)
    if not deduped_rows:
        return 0
    stmt = pg_insert(Player).values(deduped_rows)
    update_cols = {
        "full_name": func.coalesce(stmt.excluded.full_name, Player.full_name),
        "first_name": func.coalesce(stmt.excluded.first_name, Player.first_name),
        "last_name": func.coalesce(stmt.excluded.last_name, Player.last_name),
        "bats": func.coalesce(stmt.excluded.bats, Player.bats),
        "throws": func.coalesce(stmt.excluded.throws, Player.throws),
        "primary_position": func.coalesce(
            stmt.excluded.primary_position,
            Player.primary_position,
        ),
        "active": func.coalesce(stmt.excluded.active, Player.active),
        "updated_at": func.now(),
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=[Player.mlbam_id],
        set_=update_cols,
    )
    session.execute(stmt)
    return len(deduped_rows)


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
