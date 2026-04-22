"""Teams seeding — VCR-cassette-backed tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import vcr
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.ingestion.parks import seed_parks
from src.ingestion.teams import seed_teams

CASSETTES = Path(__file__).parent / "cassettes"

_vcr = vcr.VCR(
    cassette_library_dir=str(CASSETTES),
    record_mode="new_episodes",
    match_on=["method", "scheme", "host", "port", "path", "query"],
    filter_headers=["user-agent", "authorization"],
)


@pytest.fixture()
def teams_session(test_engine: Engine, clean_tables) -> sessionmaker:
    return sessionmaker(bind=test_engine, future=True, expire_on_commit=False)


def test_seed_teams_populates_thirty_teams(teams_session) -> None:
    with _vcr.use_cassette("venues_2021_2026.yaml"):
        with teams_session() as s:
            seed_parks(s, seasons=(2024,))
            s.commit()
    with _vcr.use_cassette("teams_2024.yaml"):
        with teams_session() as s:
            result = seed_teams(s, season=2024)
            s.commit()
    assert result.total == 30

    with teams_session() as s:
        count = s.execute(text("SELECT COUNT(*) FROM teams")).scalar_one()
        assert count == 30


def test_seed_teams_is_idempotent(teams_session) -> None:
    with _vcr.use_cassette("venues_2021_2026.yaml"):
        with teams_session() as s:
            seed_parks(s, seasons=(2024,))
            s.commit()
    with _vcr.use_cassette("teams_2024.yaml"):
        with teams_session() as s:
            seed_teams(s, season=2024)
            s.commit()
        with teams_session() as s:
            seed_teams(s, season=2024)
            s.commit()

    with teams_session() as s:
        count = s.execute(text("SELECT COUNT(*) FROM teams")).scalar_one()
        assert count == 30


def test_seed_teams_writes_league_and_division(teams_session) -> None:
    with _vcr.use_cassette("venues_2021_2026.yaml"):
        with teams_session() as s:
            seed_parks(s, seasons=(2024,))
            s.commit()
    with _vcr.use_cassette("teams_2024.yaml"):
        with teams_session() as s:
            seed_teams(s, season=2024)
            s.commit()

    with teams_session() as s:
        row = s.execute(
            text("SELECT league, division FROM teams WHERE team_id = 147")
        ).one_or_none()
    assert row is not None
    assert row.league and "American" in row.league
    assert row.division and "East" in row.division
