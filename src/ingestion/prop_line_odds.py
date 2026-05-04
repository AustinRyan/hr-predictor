"""Persist PropLine MLB batter home-run odds into Postgres."""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from src.core.db import get_engine
from src.core.models import OddsSnapshot
from src.ingestion.prop_line_client import (
    PropLineClient,
    PropLineEvent,
    PropLineEventOdds,
    flatten_batter_home_run_odds,
)

_log = logging.getLogger(__name__)

_SPORT_KEY = "baseball_mlb"
_MARKETS = ("batter_home_runs",)
_API_KEY_QUERY_RE = re.compile(r"([?&]apiKey=)[^&\s]+", re.IGNORECASE)


class PropLineOddsClient(Protocol):
    def fetch_events(self, sport_key: str) -> list[PropLineEvent]: ...

    def fetch_event_odds(
        self,
        *,
        sport_key: str,
        event_id: str,
        markets: tuple[str, ...],
    ) -> PropLineEventOdds: ...


@dataclass(slots=True, frozen=True)
class OddsIngestionReport:
    target_date: date
    events_seen: int = 0
    events_matched: int = 0
    rows_seen: int = 0
    rows_written: int = 0
    unmatched_events: list[str] = field(default_factory=list)
    unmatched_players: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def _normalize_name(value: str | None) -> str:
    if not value:
        return ""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    ascii_value = re.sub(r"[^a-zA-Z0-9 ]+", " ", ascii_value)
    ascii_value = re.sub(r"\b(jr|sr|ii|iii|iv)\b", " ", ascii_value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", ascii_value).strip().lower()


def _snapshot_key(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _failure_message(scope: str, exc: BaseException) -> str:
    message = str(exc) or exc.__class__.__name__
    redacted = _API_KEY_QUERY_RE.sub(r"\1***", message)
    return f"{scope}: {redacted}"


def _load_schedule_map(engine: Engine, target_date: date) -> dict[tuple[str, str], int]:
    sql = text("""
        SELECT ds.game_pk, home.name AS home_name, away.name AS away_name
        FROM daily_schedule ds
        JOIN teams home ON home.team_id = ds.home_team_id
        JOIN teams away ON away.team_id = ds.away_team_id
        WHERE ds.game_date = :target_date
        """)
    with engine.connect() as c:
        rows = c.execute(sql, {"target_date": target_date}).mappings().all()
    out: dict[tuple[str, str], int] = {}
    for row in rows:
        out[(_normalize_name(row["home_name"]), _normalize_name(row["away_name"]))] = int(
            row["game_pk"]
        )
    return out


def _load_player_map(engine: Engine) -> dict[str, int]:
    with engine.connect() as c:
        rows = (
            c.execute(text("SELECT mlbam_id, full_name FROM players WHERE full_name IS NOT NULL"))
            .mappings()
            .all()
        )
    return {_normalize_name(row["full_name"]): int(row["mlbam_id"]) for row in rows}


def persist_mlb_batter_hr_odds(
    target_date: date,
    *,
    engine: Engine | None = None,
    client: PropLineOddsClient | None = None,
    fetched_at: datetime | None = None,
) -> OddsIngestionReport:
    """Fetch and persist MLB batter home-run odds for a slate date."""
    engine = engine or get_engine()
    client = client or PropLineClient()
    fetched_at = fetched_at or datetime.now(UTC)

    schedule_map = _load_schedule_map(engine, target_date)
    player_map = _load_player_map(engine)
    try:
        events = client.fetch_events(_SPORT_KEY)
    except Exception as exc:  # noqa: BLE001
        report = OddsIngestionReport(
            target_date=target_date,
            failures=[_failure_message("fetch_events", exc)],
        )
        _log.warning(
            "prop line odds event fetch failed: %s",
            report.failures[0],
            extra={
                "target_date": target_date.isoformat(),
                "failures": report.failures,
            },
        )
        return report

    rows_to_write: list[dict] = []
    unmatched_events: list[str] = []
    unmatched_players: set[str] = set()
    failures: list[str] = []
    events_matched = 0
    rows_seen = 0

    for event in events:
        game_pk = schedule_map.get(
            (_normalize_name(event.home_team), _normalize_name(event.away_team))
        )
        if game_pk is None:
            unmatched_events.append(event.event_id)
            continue
        events_matched += 1
        try:
            event_odds = client.fetch_event_odds(
                sport_key=_SPORT_KEY,
                event_id=event.event_id,
                markets=_MARKETS,
            )
        except Exception as exc:  # noqa: BLE001
            failures.append(_failure_message(event.event_id, exc))
            continue

        flat_rows = flatten_batter_home_run_odds(event_odds, fetched_at=fetched_at)
        rows_seen += len(flat_rows)
        for row in flat_rows:
            batter_id = player_map.get(_normalize_name(row.player_name))
            if batter_id is None:
                unmatched_players.add(row.player_name)
            last_update = row.market_last_update.isoformat() if row.market_last_update else ""
            point = "" if row.point is None else f"{row.point:g}"
            key = _snapshot_key(
                [
                    row.provider,
                    row.event_id,
                    row.bookmaker_key,
                    row.market_key,
                    row.outcome_name,
                    row.player_name,
                    point,
                    str(row.price_american),
                    last_update,
                ]
            )
            rows_to_write.append(
                {
                    "snapshot_key": key,
                    "provider": row.provider,
                    "sport_key": row.sport_key,
                    "event_id": row.event_id,
                    "game_pk": game_pk,
                    "game_date": target_date,
                    "commence_time": row.commence_time,
                    "home_team": row.home_team,
                    "away_team": row.away_team,
                    "bookmaker_key": row.bookmaker_key,
                    "bookmaker_title": row.bookmaker_title,
                    "market_key": row.market_key,
                    "outcome_name": row.outcome_name,
                    "player_name": row.player_name,
                    "batter_id": batter_id,
                    "price_american": row.price_american,
                    "point": row.point,
                    "implied_probability": row.implied_probability,
                    "no_vig_probability": row.no_vig_probability,
                    "market_last_update": row.market_last_update,
                    "fetched_at": fetched_at,
                    "raw_outcome": row.raw_outcome,
                }
            )

    if rows_to_write:
        session_factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
        with session_factory() as s:
            stmt = pg_insert(OddsSnapshot).values(rows_to_write)
            update_cols = {
                c.name: getattr(stmt.excluded, c.name)
                for c in OddsSnapshot.__table__.columns
                if c.name not in {"id", "snapshot_key"}
            }
            s.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_odds_snapshots_snapshot_key",
                    set_=update_cols,
                )
            )
            s.commit()

    report = OddsIngestionReport(
        target_date=target_date,
        events_seen=len(events),
        events_matched=events_matched,
        rows_seen=rows_seen,
        rows_written=len(rows_to_write),
        unmatched_events=unmatched_events,
        unmatched_players=sorted(unmatched_players),
        failures=failures,
    )
    _log.info(
        "prop line odds persisted",
        extra={
            "target_date": target_date.isoformat(),
            "events_seen": report.events_seen,
            "events_matched": report.events_matched,
            "rows_seen": report.rows_seen,
            "rows_written": report.rows_written,
            "failures": report.failures,
        },
    )
    return report


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Fetch PropLine MLB batter HR odds")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    report = persist_mlb_batter_hr_odds(args.date)
    print(
        "odds rows="
        f"{report.rows_written} events={report.events_matched}/{report.events_seen} "
        f"unmatched_players={len(report.unmatched_players)} failures={report.failures}",
        flush=True,
    )


if __name__ == "__main__":
    main()
