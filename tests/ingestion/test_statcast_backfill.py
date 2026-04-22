"""Backfill loader tests.

Hybrid strategy:
* VCR cassette records one real day (2024-04-10) for idempotency and
  per-day-load assertions.
* Resume behavior is tested against a fully-synthetic fixture so no
  network is required.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import vcr
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.core.models import IngestionState
from src.ingestion import statcast_backfill as backfill_mod
from src.ingestion.statcast_backfill import (
    BACKFILL_KEY,
    _frame_to_rows,
    backfill_statcast,
)

CASSETTES = Path(__file__).parent / "cassettes"
CASSETTES.mkdir(exist_ok=True)

_vcr = vcr.VCR(
    cassette_library_dir=str(CASSETTES),
    record_mode="new_episodes",
    match_on=["method", "scheme", "host", "port", "path", "query"],
    filter_headers=["user-agent", "authorization"],
)


def test_frame_to_rows_handles_empty() -> None:
    import pandas as pd

    assert _frame_to_rows(pd.DataFrame(), date(2024, 4, 10)) == []
    assert _frame_to_rows(None, date(2024, 4, 10)) == []  # type: ignore[arg-type]


def test_frame_to_rows_drops_wrong_day() -> None:
    import pandas as pd

    frame = pd.DataFrame(
        [
            {
                "game_date": "2024-04-10",
                "game_pk": 1,
                "at_bat_number": 1,
                "pitch_number": 1,
                "batter": 100,
                "pitcher": 200,
                "pitch_type": "FF",
                "launch_speed": 95.0,
            },
            {
                # Off-by-one day that slipped into the daily frame.
                "game_date": "2024-04-09",
                "game_pk": 2,
                "at_bat_number": 1,
                "pitch_number": 1,
                "batter": 101,
                "pitcher": 201,
                "pitch_type": "SL",
                "launch_speed": None,
            },
        ]
    )
    rows = _frame_to_rows(frame, date(2024, 4, 10))
    assert len(rows) == 1
    assert rows[0]["game_pk"] == 1


def test_frame_to_rows_deduplicates_on_pk() -> None:
    import pandas as pd

    frame = pd.DataFrame(
        [
            {
                "game_date": "2024-04-10",
                "game_pk": 1,
                "at_bat_number": 1,
                "pitch_number": 1,
                "batter": 100,
                "pitcher": 200,
                "launch_speed": 90.0,
            },
            {
                "game_date": "2024-04-10",
                "game_pk": 1,
                "at_bat_number": 1,
                "pitch_number": 1,
                "batter": 100,
                "pitcher": 200,
                "launch_speed": 95.0,  # later/corrected reading wins
            },
        ]
    )
    rows = _frame_to_rows(frame, date(2024, 4, 10))
    assert len(rows) == 1
    assert rows[0]["launch_speed"] == 95.0


@pytest.fixture()
def fresh_test_engine(seeded_parks_teams: Engine):
    return seeded_parks_teams


@pytest.mark.integration
def test_backfill_one_day_is_idempotent(
    fresh_test_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _vcr.use_cassette("statcast_backfill_2024-04-10.yaml"):
        report1 = backfill_statcast(
            date(2024, 4, 10),
            date(2024, 4, 10),
            resume=False,
            engine=fresh_test_engine,
            day_sleep=0,
        )
    assert report1.total_pitches > 0
    assert report1.total_games > 0
    assert report1.days_processed == 1

    with _vcr.use_cassette("statcast_backfill_2024-04-10.yaml"):
        report2 = backfill_statcast(
            date(2024, 4, 10),
            date(2024, 4, 10),
            resume=False,
            engine=fresh_test_engine,
            day_sleep=0,
        )

    # Second run should upsert the same rows (same count), add no new
    # players, and keep totals stable in the DB.
    with fresh_test_engine.connect() as c:
        pitch_count = c.execute(text("SELECT COUNT(*) FROM statcast_pitches")).scalar_one()
        game_count = c.execute(text("SELECT COUNT(*) FROM games")).scalar_one()
    assert pitch_count == report1.total_pitches
    assert game_count == report1.total_games
    assert report2.total_new_players == 0


@pytest.mark.integration
def test_backfill_resume_skips_completed_days(
    fresh_test_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Pre-seed ingestion_state so the loader thinks 2024-04-10 is done.
    Session_ = sessionmaker(bind=fresh_test_engine, future=True, expire_on_commit=False)
    with Session_() as s:
        s.add(
            IngestionState(
                operation_key=BACKFILL_KEY,
                last_completed_date=date(2024, 4, 10),
                status="running",
            )
        )
        s.commit()

    # Stub the external calls so the test breaks loudly if resume fails.
    def _boom(*a, **k):
        raise AssertionError("resume should have skipped 2024-04-10")

    monkeypatch.setattr(backfill_mod, "fetch_schedule", _boom)
    monkeypatch.setattr(backfill_mod.pybaseball, "statcast", _boom)

    report = backfill_statcast(
        date(2024, 4, 10),
        date(2024, 4, 10),
        resume=True,
        engine=fresh_test_engine,
        day_sleep=0,
    )
    assert report.days_processed == 0
    assert report.days_skipped_resume == 1


def test_backfill_rejects_inverted_range() -> None:
    with pytest.raises(ValueError):
        backfill_statcast(date(2024, 4, 10), date(2024, 4, 9), resume=False)
