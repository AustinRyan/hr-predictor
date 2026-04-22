"""VCR-backed tests for Phase 2 StatsAPI client functions."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import vcr
from src.ingestion.mlb_statsapi_client import (
    fetch_boxscore,
    fetch_game_content,
    fetch_schedule_with_probables,
)

CASSETTES = Path(__file__).parent / "cassettes"
CASSETTES.mkdir(exist_ok=True)

_vcr = vcr.VCR(
    cassette_library_dir=str(CASSETTES),
    record_mode="new_episodes",
    match_on=["method", "scheme", "host", "port", "path", "query"],
    filter_headers=["user-agent", "authorization"],
)

# Real Final game from 2024-04-10 — recorded into cassettes below.
# Minnesota Twins vs Los Angeles Dodgers at Target Field.
_GAME_PK_2024_04_10_FINAL = 745923


def test_fetch_schedule_with_probables_returns_probable_ids() -> None:
    with _vcr.use_cassette("statsapi_schedule_probables_2024-04-10.yaml"):
        games = list(fetch_schedule_with_probables(date(2024, 4, 10), date(2024, 4, 10)))
    assert len(games) >= 10  # ~15 games on a normal April day
    # At least one game should have both probable pitchers populated by game time.
    with_both = [g for g in games if g.home_probable_pitcher_id and g.away_probable_pitcher_id]
    assert len(with_both) >= 1


def test_fetch_boxscore_returns_batting_order() -> None:
    with _vcr.use_cassette(f"statsapi_boxscore_{_GAME_PK_2024_04_10_FINAL}.yaml"):
        bx = fetch_boxscore(_GAME_PK_2024_04_10_FINAL)
    # Completed games always have 9-man lineups.
    assert len(bx.teams.home.batting_order) == 9
    assert len(bx.teams.away.batting_order) == 9


def test_fetch_game_content_roof_status_is_string_or_none() -> None:
    with _vcr.use_cassette(f"statsapi_game_{_GAME_PK_2024_04_10_FINAL}.yaml"):
        roof = fetch_game_content(_GAME_PK_2024_04_10_FINAL)
    assert roof is None or isinstance(roof, str)
