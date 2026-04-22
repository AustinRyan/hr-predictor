"""Team seeding from MLB StatsAPI."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.core.models import Team
from src.ingestion.mlb_statsapi_client import fetch_teams

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class TeamSeedResult:
    total: int


def seed_teams(session: Session, season: int | None = None) -> TeamSeedResult:
    """Upsert the 30 MLB teams for the given season.

    Defaults to the current year; Phase 2 daily ingestion can re-call this to
    refresh each year's metadata in case divisions or names change.
    """
    resolved = season or date.today().year
    resp = fetch_teams(resolved)

    rows = []
    for t in resp.teams:
        venue_id = t.venue.id if t.venue else None
        league = t.league.name if t.league else None
        division = t.division.name if t.division else None
        rows.append(
            {
                "team_id": t.id,
                "abbr": (t.abbreviation or "")[:4],
                "name": t.name,
                "home_park_id": venue_id,
                "league": league,
                "division": division,
            }
        )

    if not rows:
        _log.warning("no teams returned by StatsAPI", extra={"season": resolved})
        return TeamSeedResult(total=0)

    stmt = pg_insert(Team).values(rows)
    update_cols = {
        c.name: getattr(stmt.excluded, c.name)
        for c in Team.__table__.columns
        if c.name not in {"team_id"}
    }
    stmt = stmt.on_conflict_do_update(index_elements=[Team.team_id], set_=update_cols)
    session.execute(stmt)

    _log.info("teams seeded", extra={"season": resolved, "total": len(rows)})
    return TeamSeedResult(total=len(rows))
