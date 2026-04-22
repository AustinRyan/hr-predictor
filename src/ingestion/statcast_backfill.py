"""Resumable, idempotent Statcast pitch-level backfill.

Pulls pybaseball `statcast()` one day at a time, upserts into the
partitioned `statcast_pitches` table, lazy-populates `players` from
observed batter/pitcher IDs, and writes `games` rows from MLB StatsAPI
schedule. Resume state is held in `ingestion_state`.

Invariants
----------
* One DB transaction per day. A day either fully lands or doesn't.
* Re-running over an already-loaded range produces zero row deltas.
* On any per-day failure we mark state `failed`, log the exception, and
  stop — operator re-runs to resume.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import pybaseball
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.db import get_engine
from src.core.models import Game, IngestionState, Player, StatcastPitch
from src.ingestion.mlb_statsapi_client import fetch_schedule
from src.ingestion.wire_models import ScheduleGame

_log = logging.getLogger(__name__)

BACKFILL_KEY = "statcast_backfill"

# Columns in pybaseball's statcast frame that we persist. Any column in
# this list that is absent from the frame for a given day is treated as
# NULL — defends against Savant schema drift.
_PITCH_COLUMNS: tuple[str, ...] = (
    "game_date",
    "game_pk",
    "at_bat_number",
    "pitch_number",
    "batter",
    "pitcher",
    "pitch_type",
    "release_speed",
    "release_spin_rate",
    "effective_speed",
    "launch_speed",
    "launch_angle",
    "hit_distance_sc",
    "hc_x",
    "hc_y",
    "events",
    "description",
    "balls",
    "strikes",
    "outs_when_up",
    "inning",
    "inning_topbot",
    "stand",
    "p_throws",
    "estimated_woba_using_speedangle",
    "estimated_ba_using_speedangle",
    "woba_value",
    "woba_denom",
    "launch_speed_angle",
    "zone",
    "plate_x",
    "plate_z",
    "home_team",
    "away_team",
    "bat_speed",
    "swing_length",
)

_INT_COLUMNS: frozenset[str] = frozenset(
    {
        "game_pk",
        "at_bat_number",
        "pitch_number",
        "batter",
        "pitcher",
        "release_spin_rate",
        "balls",
        "strikes",
        "outs_when_up",
        "inning",
        "launch_speed_angle",
        "zone",
    }
)

_STRING_COLUMNS: frozenset[str] = frozenset(
    {
        "pitch_type",
        "events",
        "description",
        "inning_topbot",
        "stand",
        "p_throws",
        "home_team",
        "away_team",
    }
)


@dataclass(slots=True)
class DayLoadResult:
    day: date
    pitches_loaded: int
    games_upserted: int
    new_players: int
    elapsed_seconds: float


@dataclass(slots=True)
class BackfillReport:
    start_date: date
    end_date: date
    days_processed: int = 0
    days_skipped_resume: int = 0
    total_pitches: int = 0
    total_games: int = 0
    total_new_players: int = 0
    elapsed_seconds: float = 0.0
    failures: list[tuple[date, str]] = field(default_factory=list)


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------


def backfill_statcast(
    start_date: date,
    end_date: date,
    *,
    resume: bool = True,
    engine: Engine | None = None,
    day_sleep: float = 1.0,
) -> BackfillReport:
    """Backfill pitches for every day in [start_date, end_date] inclusive."""
    if end_date < start_date:
        raise ValueError(f"end_date ({end_date}) precedes start_date ({start_date})")

    pybaseball.cache.enable()
    engine = engine or get_engine()
    Session_ = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    report = BackfillReport(start_date=start_date, end_date=end_date)
    run_started = time.monotonic()

    resume_marker = _load_resume_marker(Session_) if resume else None
    if resume_marker is not None:
        _log.info("resuming backfill", extra={"last_completed": resume_marker.isoformat()})

    for day in _iter_days(start_date, end_date):
        if resume and resume_marker is not None and day <= resume_marker:
            report.days_skipped_resume += 1
            continue

        try:
            result = _load_day(Session_, day)
        except Exception as exc:  # pragma: no cover - surfaced via report
            _log.exception("day load failed", extra={"day": day.isoformat()})
            _mark_failed(Session_, day, str(exc))
            report.failures.append((day, repr(exc)))
            break

        report.days_processed += 1
        report.total_pitches += result.pitches_loaded
        report.total_games += result.games_upserted
        report.total_new_players += result.new_players

        _log.info(
            "day complete",
            extra={
                "day": day.isoformat(),
                "pitches": result.pitches_loaded,
                "games": result.games_upserted,
                "new_players": result.new_players,
                "elapsed_s": round(result.elapsed_seconds, 2),
            },
        )

        if day_sleep > 0 and day != end_date:
            time.sleep(day_sleep)

    report.elapsed_seconds = time.monotonic() - run_started
    _log.info(
        "backfill complete",
        extra={
            "days_processed": report.days_processed,
            "days_skipped": report.days_skipped_resume,
            "pitches": report.total_pitches,
            "games": report.total_games,
            "elapsed_s": round(report.elapsed_seconds, 1),
        },
    )
    return report


# ----------------------------------------------------------------------
# Per-day load
# ----------------------------------------------------------------------


def _load_day(Session_: sessionmaker, day: date) -> DayLoadResult:
    started = time.monotonic()
    start_iso = day.isoformat()

    # Games first (safe even on 0-game days — spring training off days).
    schedule = fetch_schedule(day, day)
    schedule_games = list(schedule.iter_games())

    # Statcast second. pybaseball returns a DataFrame (possibly empty).
    df = pybaseball.statcast(start_iso, start_iso)
    pitch_rows = _frame_to_rows(df, day)

    new_player_ids = _collect_new_player_ids(pitch_rows)

    with Session_() as session:
        games_upserted = _upsert_games(session, schedule_games)
        pitches_loaded = _upsert_pitches(session, pitch_rows)
        new_players = _upsert_players(session, new_player_ids)
        _mark_day_completed(session, day)
        session.commit()

    return DayLoadResult(
        day=day,
        pitches_loaded=pitches_loaded,
        games_upserted=games_upserted,
        new_players=new_players,
        elapsed_seconds=time.monotonic() - started,
    )


# ----------------------------------------------------------------------
# DataFrame → row tuples
# ----------------------------------------------------------------------


def _frame_to_rows(df: pd.DataFrame, day: date) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []

    keep = [c for c in _PITCH_COLUMNS if c in df.columns]
    sub = df[keep].copy()

    # Normalize game_date to python date regardless of pandas dtype.
    if "game_date" in sub.columns:
        sub["game_date"] = pd.to_datetime(sub["game_date"]).dt.date

    rows: list[dict[str, Any]] = []
    # Iterate as records and hand-clean: pandas → Python type coercion is
    # annoying with nullable Int64 + NaN + numpy ints.
    for rec in sub.to_dict(orient="records"):
        cleaned: dict[str, Any] = {}
        for col in _PITCH_COLUMNS:
            val = rec.get(col)
            cleaned[col] = _clean(col, val)
        if cleaned["game_date"] != day:
            # Defensive: Savant occasionally reports UTC-next-day rows under
            # a given game date. Trust the column, skip day mismatches silently.
            continue
        if cleaned["game_pk"] is None or cleaned["at_bat_number"] is None:
            continue
        if cleaned["pitch_number"] is None:
            continue
        rows.append(cleaned)

    # Deduplicate on the composite PK — Savant sometimes emits repeated
    # rows for reviewed plays. Last write wins (same as ON CONFLICT).
    dedup: dict[tuple, dict] = {}
    for r in rows:
        key = (r["game_date"], r["game_pk"], r["at_bat_number"], r["pitch_number"])
        dedup[key] = r
    return list(dedup.values())


def _clean(col: str, val: Any) -> Any:
    if val is None:
        return None
    # pandas NA / NaN
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if col in _INT_COLUMNS:
        try:
            return int(val)
        except (TypeError, ValueError):
            return None
    if col in _STRING_COLUMNS:
        s = str(val).strip()
        return s or None
    # Floats: coerce numpy types → Python floats for psycopg
    if isinstance(val, int | float):
        return float(val) if col not in _INT_COLUMNS else int(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return val


# ----------------------------------------------------------------------
# Upserts
# ----------------------------------------------------------------------


def _upsert_pitches(session: Session, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    # Chunk to keep parameter count under psycopg's limits.
    chunk_size = 500
    total = 0
    pk_cols = ["game_date", "game_pk", "at_bat_number", "pitch_number"]
    non_pk_cols = [c for c in _PITCH_COLUMNS if c not in pk_cols]

    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        stmt = pg_insert(StatcastPitch).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=pk_cols,
            set_={c: getattr(stmt.excluded, c) for c in non_pk_cols},
        )
        session.execute(stmt)
        total += len(chunk)
    return total


def _upsert_games(session: Session, games: Iterable[ScheduleGame]) -> int:
    rows: list[dict[str, Any]] = []
    for g in games:
        official = g.official_date or g.game_date.date()
        home = (g.teams.home or {}) if g.teams else {}
        away = (g.teams.away or {}) if g.teams else {}
        home_team_id = _safe_int((home.get("team") or {}).get("id"))
        away_team_id = _safe_int((away.get("team") or {}).get("id"))
        venue_id = g.venue.id if g.venue else None
        season = int(g.season) if g.season and g.season.isdigit() else official.year
        status = None
        if g.status is not None:
            status = g.status.detailed_state or g.status.abstract_game_state

        rows.append(
            {
                "game_pk": g.game_pk,
                "game_date": official,
                "season": season,
                "home_team_id": home_team_id,
                "away_team_id": away_team_id,
                "venue_id": venue_id,
                "game_type": g.game_type,
                "day_night": _day_night_letter(g.day_night),
                "game_start_utc": g.game_date,
                "status": (status or "")[:24] or None,
            }
        )

    if not rows:
        return 0

    stmt = pg_insert(Game).values(rows)
    update_cols = {
        c.name: getattr(stmt.excluded, c.name)
        for c in Game.__table__.columns
        if c.name not in {"game_pk"}
    }
    stmt = stmt.on_conflict_do_update(index_elements=[Game.game_pk], set_=update_cols)
    session.execute(stmt)
    return len(rows)


def _upsert_players(session: Session, new_ids: set[int]) -> int:
    if not new_ids:
        return 0

    existing = set(
        session.execute(select(Player.mlbam_id).where(Player.mlbam_id.in_(new_ids))).scalars()
    )
    truly_new = sorted(new_ids - existing)
    if not truly_new:
        return 0

    enriched = _enrich_players(truly_new)
    rows = []
    for mlbam_id in truly_new:
        info = enriched.get(mlbam_id, {})
        rows.append(
            {
                "mlbam_id": mlbam_id,
                "full_name": info.get("full_name"),
                "first_name": info.get("first_name"),
                "last_name": info.get("last_name"),
                "active": True,
            }
        )

    stmt = pg_insert(Player).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=[Player.mlbam_id])
    session.execute(stmt)
    return len(rows)


def _enrich_players(mlbam_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Call pybaseball.playerid_reverse_lookup in batches; tolerate failure."""
    if not mlbam_ids:
        return {}
    out: dict[int, dict[str, Any]] = {}
    batch_size = 50
    for i in range(0, len(mlbam_ids), batch_size):
        batch = mlbam_ids[i : i + batch_size]
        try:
            df = pybaseball.playerid_reverse_lookup(batch, key_type="mlbam")
        except Exception as exc:  # pragma: no cover - network dependent
            _log.warning(
                "playerid_reverse_lookup failed",
                extra={"batch_size": len(batch), "err": str(exc)},
            )
            continue
        for rec in df.to_dict(orient="records"):
            mid = _safe_int(rec.get("key_mlbam"))
            if mid is None:
                continue
            first = (rec.get("name_first") or "").strip() or None
            last = (rec.get("name_last") or "").strip() or None
            full = None
            if first or last:
                full = " ".join(p for p in (first, last) if p)
            out[mid] = {"first_name": first, "last_name": last, "full_name": full}
    return out


def _collect_new_player_ids(rows: list[dict[str, Any]]) -> set[int]:
    ids: set[int] = set()
    for r in rows:
        b = r.get("batter")
        p = r.get("pitcher")
        if isinstance(b, int):
            ids.add(b)
        if isinstance(p, int):
            ids.add(p)
    return ids


# ----------------------------------------------------------------------
# Resume state
# ----------------------------------------------------------------------


def _load_resume_marker(Session_: sessionmaker) -> date | None:
    with Session_() as session:
        state = session.get(IngestionState, BACKFILL_KEY)
        return state.last_completed_date if state else None


def _mark_day_completed(session: Session, day: date) -> None:
    state = session.get(IngestionState, BACKFILL_KEY)
    if state is None:
        state = IngestionState(operation_key=BACKFILL_KEY)
        session.add(state)
    if state.last_completed_date is None or day > state.last_completed_date:
        state.last_completed_date = day
    state.status = "running"
    state.error_message = None
    state.updated_at = datetime.now(UTC)


def _mark_failed(Session_: sessionmaker, day: date, error: str) -> None:
    with Session_() as session:
        state = session.get(IngestionState, BACKFILL_KEY)
        if state is None:
            state = IngestionState(operation_key=BACKFILL_KEY)
            session.add(state)
        state.status = "failed"
        state.error_message = f"{day.isoformat()}: {error}"[:2048]
        state.updated_at = datetime.now(UTC)
        session.commit()


def mark_complete(engine: Engine | None = None) -> None:
    """Flip the backfill state to complete (call after final day succeeds)."""
    engine = engine or get_engine()
    Session_ = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with Session_() as session:
        state = session.get(IngestionState, BACKFILL_KEY)
        if state is None:
            return
        state.status = "complete"
        state.error_message = None
        state.updated_at = datetime.now(UTC)
        session.commit()


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _iter_days(start: date, end: date) -> Iterator[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _day_night_letter(val: str | None) -> str | None:
    if not val:
        return None
    s = val.strip().lower()
    if s.startswith("d"):
        return "D"
    if s.startswith("n"):
        return "N"
    return None


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def main() -> int:  # pragma: no cover
    import argparse

    from src.core.logging_config import configure_logging

    configure_logging()

    parser = argparse.ArgumentParser(description="Statcast backfill")
    parser.add_argument("--start", type=_parse_date, required=True)
    parser.add_argument("--end", type=_parse_date, required=True)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--sleep", type=float, default=1.0)
    args = parser.parse_args()

    report = backfill_statcast(
        args.start,
        args.end,
        resume=not args.no_resume,
        day_sleep=args.sleep,
    )
    if not report.failures and report.end_date == args.end:
        mark_complete()
    return 0 if not report.failures else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
