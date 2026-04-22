"""Park seeding.

Authoritative source for park metadata is MLB StatsAPI
(`/api/v1/venues?hydrate=location`), which exposes:

- park_id (venue.id)
- name
- city, state
- latitude, longitude
- orientation_deg (via `location.azimuthAngle` — bearing from home plate to CF)
- elevation_ft (via `location.elevation`)

StatsAPI does NOT publish roof type; we maintain a small dict keyed by
StatsAPI venue ID for the 30 primary MLB parks. Everything else defaults
to None and the feature layer is expected to gate weather features off
when roof_type is null.

Prior iteration of this file used a dict of *fabricated* park IDs
(see phases/phase1/NOTES.md "Park ID system correction"). That dict was
replaced by real StatsAPI lookups in Phase 1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.core.models import Park
from src.ingestion.mlb_statsapi_client import fetch_venues
from src.ingestion.wire_models import Venue

_log = logging.getLogger(__name__)


# StatsAPI venue IDs → roof type. Only the 30 primary MLB parks.
# Every other venue (spring training / alternates / minor league) gets
# a null roof_type — the feature layer must handle that.
ROOF_TYPES: dict[int, str] = {
    1: "open",  # Angel Stadium (Angels)
    2: "open",  # Oriole Park at Camden Yards (Orioles)
    3: "open",  # Fenway Park (Red Sox)
    4: "open",  # Rate Field / Guaranteed Rate (White Sox)
    5: "open",  # Progressive Field (Guardians)
    7: "open",  # Kauffman Stadium (Royals)
    10: "open",  # Oakland Coliseum (Athletics 2021-2024)
    12: "dome",  # Tropicana Field (Rays 2021-2024 primary)
    14: "retractable",  # Rogers Centre (Blue Jays)
    15: "retractable",  # Chase Field (Diamondbacks)
    17: "open",  # Wrigley Field (Cubs)
    19: "open",  # Coors Field (Rockies)
    22: "open",  # Dodger Stadium (Dodgers)
    31: "open",  # PNC Park (Pirates)
    32: "retractable",  # American Family Field (Brewers)
    680: "retractable",  # T-Mobile Park (Mariners)
    2392: "retractable",  # Minute Maid Park / Daikin Park (Astros)
    2394: "open",  # Comerica Park (Tigers)
    2395: "open",  # Oracle Park (Giants)
    2523: "open",  # George M. Steinbrenner Field (Rays 2025 alternate)
    2529: "open",  # Sutter Health Park (Athletics 2025 alternate)
    2602: "open",  # Great American Ball Park (Reds)
    2680: "open",  # Petco Park (Padres)
    2681: "open",  # Citizens Bank Park (Phillies)
    2889: "open",  # Busch Stadium (Cardinals)
    3289: "open",  # Citi Field (Mets)
    3309: "open",  # Nationals Park (Nationals)
    3312: "open",  # Target Field (Twins)
    3313: "open",  # Yankee Stadium (Yankees)
    4169: "retractable",  # loanDepot park (Marlins)
    4705: "open",  # Truist Park (Braves)
    5325: "retractable",  # Globe Life Field (Rangers)
}


# Seasons we seed venues for. Picks up alternate venues across the
# training window plus the current season.
DEFAULT_SEED_SEASONS: tuple[int, ...] = tuple(range(2021, date.today().year + 1))


@dataclass(slots=True)
class ParkSeedResult:
    inserted: int
    updated: int
    missing_roof_warnings: list[int]


def _venue_to_row(v: Venue) -> dict:
    loc = v.location
    row: dict[str, object | None] = {
        "park_id": v.id,
        "name": v.name,
        "city": loc.city if loc else None,
        "state": loc.state if loc else None,
        "latitude": v.latitude,
        "longitude": v.longitude,
        "orientation_deg": loc.azimuth_angle if loc else None,
        "elevation_ft": loc.elevation if loc else None,
        "roof_type": ROOF_TYPES.get(v.id),
    }
    return row


def seed_parks(
    session: Session,
    seasons: tuple[int, ...] = DEFAULT_SEED_SEASONS,
) -> ParkSeedResult:
    """Upsert every venue observed across `seasons` from MLB StatsAPI.

    Idempotent: re-running produces the same state. `updated_at` advances
    on every upsert; no other columns drift unless the upstream data
    changes.
    """
    collected: dict[int, Venue] = {}
    for season in seasons:
        _log.info("fetching venues", extra={"season": season})
        for v in fetch_venues(season):
            collected[v.id] = v

    # Pre-read existing IDs so we can report insert vs. update counts.
    existing_ids = set(session.execute(select(Park.park_id)).scalars().all())

    rows = [_venue_to_row(v) for v in collected.values()]
    stmt = pg_insert(Park).values(rows)
    update_cols = {
        c.name: getattr(stmt.excluded, c.name)
        for c in Park.__table__.columns
        if c.name not in {"park_id", "created_at"}
    }
    stmt = stmt.on_conflict_do_update(index_elements=[Park.park_id], set_=update_cols)
    session.execute(stmt)

    inserted = sum(1 for r in rows if r["park_id"] not in existing_ids)
    updated = len(rows) - inserted

    # Flag venues that are primary-roster candidates but missing roof_type.
    # (Anything in ROOF_TYPES is covered by definition; warn on id ranges
    # that look "primary" but are missing.)
    primary_missing: list[int] = []
    for v in collected.values():
        if v.id in ROOF_TYPES:
            continue
        if v.location and v.location.azimuth_angle is not None and v.active:
            # A venue StatsAPI says is active and oriented but we don't
            # classify — surface for review.
            primary_missing.append(v.id)

    if primary_missing:
        _log.info(
            "venues seeded without roof_type (expected for alternates/spring-training)",
            extra={"venue_ids": sorted(primary_missing)},
        )

    result = ParkSeedResult(
        inserted=inserted,
        updated=updated,
        missing_roof_warnings=sorted(primary_missing),
    )
    _log.info(
        "parks seeded",
        extra={"inserted": result.inserted, "updated": result.updated, "total": len(rows)},
    )
    return result
