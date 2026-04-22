"""Parks seeding — VCR-cassette-backed tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import vcr
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.ingestion.parks import ROOF_TYPES, seed_parks

CASSETTES = Path(__file__).parent / "cassettes"
CASSETTES.mkdir(exist_ok=True)

_vcr = vcr.VCR(
    cassette_library_dir=str(CASSETTES),
    record_mode="new_episodes",
    match_on=["method", "scheme", "host", "port", "path", "query"],
    filter_headers=["user-agent", "authorization"],
)


@pytest.fixture()
def parks_session(test_engine: Engine, clean_tables) -> sessionmaker:
    return sessionmaker(bind=test_engine, future=True, expire_on_commit=False)


def test_seed_parks_populates_primary_mlb_parks(parks_session) -> None:
    with _vcr.use_cassette("venues_2021_2026.yaml"):
        with parks_session() as s:
            # Seed one season to keep the cassette small; ROOF_TYPES list
            # is keyed by StatsAPI venue ids which are stable year-to-year.
            result = seed_parks(s, seasons=(2024,))
            s.commit()
        assert result.inserted > 0

    with parks_session() as s:
        # Every primary MLB park key we classify in ROOF_TYPES must now
        # exist in parks — except two alternate-venue IDs that only show
        # up in 2025+ schedules (Steinbrenner Field / Sutter Health). We
        # seeded only 2024 for the cassette, so filter those out here.
        always_present = {vid for vid in ROOF_TYPES if vid not in {2523, 2529}}
        rows = (
            s.execute(
                text("SELECT park_id FROM parks WHERE park_id = ANY(:ids)"),
                {"ids": sorted(always_present)},
            )
            .scalars()
            .all()
        )
        missing = always_present - set(rows)
        assert not missing, f"Missing parks: {sorted(missing)}"


def test_seed_parks_sets_orientation_and_elevation(parks_session) -> None:
    with _vcr.use_cassette("venues_2021_2026.yaml"):
        with parks_session() as s:
            seed_parks(s, seasons=(2024,))
            s.commit()

    with parks_session() as s:
        # Orientation + elevation come from StatsAPI directly; every
        # primary park should have both.
        row = s.execute(
            text("""
                SELECT COUNT(*) FROM parks
                WHERE park_id = ANY(:ids)
                  AND orientation_deg IS NOT NULL
                  AND elevation_ft IS NOT NULL
                  AND roof_type IS NOT NULL
                """),
            {"ids": sorted(vid for vid in ROOF_TYPES if vid not in {2523, 2529})},
        ).scalar_one()
        assert row == len(ROOF_TYPES) - 2


def test_seed_parks_is_idempotent(parks_session) -> None:
    with _vcr.use_cassette("venues_2021_2026.yaml"):
        with parks_session() as s:
            first = seed_parks(s, seasons=(2024,))
            s.commit()
        with parks_session() as s:
            second = seed_parks(s, seasons=(2024,))
            s.commit()

    # Second run sees everything as updates; row count should match first.
    assert second.inserted == 0
    assert second.updated == first.inserted + first.updated

    with parks_session() as s:
        total = s.execute(text("SELECT COUNT(*) FROM parks")).scalar_one()
        # No duplicates created by the second run.
        assert total == first.inserted + first.updated


def test_seed_parks_roof_dome_for_tropicana(parks_session) -> None:
    with _vcr.use_cassette("venues_2021_2026.yaml"):
        with parks_session() as s:
            seed_parks(s, seasons=(2024,))
            s.commit()

    with parks_session() as s:
        roof = s.execute(text("SELECT roof_type FROM parks WHERE park_id = 12")).scalar_one()
        assert roof == "dome"


def test_seed_parks_populates_coordinates(parks_session) -> None:
    """Regression guard: Phase 2 Task 12 discovered defaultCoordinates was silently
    dropped; this test prevents that shape change from going silent again."""
    with _vcr.use_cassette("venues_2021_2026.yaml"):
        with parks_session() as s:
            seed_parks(s, seasons=(2024,))
            s.commit()

    with parks_session() as s:
        # Coors, Yankee, Wrigley — known primary MLB parks. All must have coords.
        row = s.execute(
            text(
                "SELECT COUNT(*) FROM parks "
                "WHERE park_id = ANY(:ids) "
                "AND latitude IS NOT NULL AND longitude IS NOT NULL"
            ),
            {"ids": [19, 3313, 17]},
        ).scalar_one()
        assert row == 3, "All three reference parks must have lat/lon populated"


def test_seed_parks_retractable_roofs(parks_session) -> None:
    with _vcr.use_cassette("venues_2021_2026.yaml"):
        with parks_session() as s:
            seed_parks(s, seasons=(2024,))
            s.commit()

    retractable_ids = {
        14,  # Rogers Centre
        15,  # Chase Field
        32,  # American Family Field
        680,  # T-Mobile Park
        2392,  # Minute Maid / Daikin
        4169,  # loanDepot park
        5325,  # Globe Life Field
    }
    with parks_session() as s:
        rows = s.execute(
            text("SELECT park_id, roof_type FROM parks WHERE park_id = ANY(:ids)"),
            {"ids": sorted(retractable_ids)},
        ).all()
    mapping = {r.park_id: r.roof_type for r in rows}
    for pid in retractable_ids:
        assert mapping.get(pid) == "retractable", (pid, mapping.get(pid))
