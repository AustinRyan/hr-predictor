"""Integration tests for the daily-schedule orchestrator.

Strategy: the live-API response shape is already exercised by the Task 4
VCR cassettes in `test_mlb_statsapi_client_phase2.py`. Here we stub the
client fetchers and exercise the orchestration contract (upsert
idempotency, doubleheader handling, roof-status propagation, etc.)
against a real Postgres.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from src.ingestion import mlb_statsapi as orchestrator
from src.ingestion.mlb_statsapi import persist_daily_schedule
from src.ingestion.wire_models import (
    BoxscoreResponse,
    BoxscoreTeamRef,
    BoxscoreTeams,
    BoxscoreTeamSide,
    ScheduleGameWithProbables,
)


def _make_game(
    *,
    game_pk: int,
    home_team_id: int = 147,
    away_team_id: int = 117,
    venue_id: int = 3313,
    home_probable: int | None = 656756,
    away_probable: int | None = 543037,
    game_start: datetime | None = None,
) -> ScheduleGameWithProbables:
    start = game_start or datetime(2026, 4, 22, 23, 10, tzinfo=UTC)
    return ScheduleGameWithProbables.model_validate(
        {
            "gamePk": game_pk,
            "gameDate": start.isoformat().replace("+00:00", "Z"),
            "officialDate": start.date().isoformat(),
            "teams": {
                "home": {
                    "team": {"id": home_team_id},
                    **(
                        {"probablePitcher": {"id": home_probable}}
                        if home_probable is not None
                        else {}
                    ),
                },
                "away": {
                    "team": {"id": away_team_id},
                    **(
                        {"probablePitcher": {"id": away_probable}}
                        if away_probable is not None
                        else {}
                    ),
                },
            },
            "venue": {"id": venue_id},
            "status": {"detailedState": "Scheduled"},
        }
    )


def _make_boxscore(home_team_id: int, away_team_id: int, order_size: int = 9) -> BoxscoreResponse:
    return BoxscoreResponse(
        teams=BoxscoreTeams(
            home=BoxscoreTeamSide(
                team=BoxscoreTeamRef(id=home_team_id),
                batting_order=list(range(100001, 100001 + order_size)),
            ),
            away=BoxscoreTeamSide(
                team=BoxscoreTeamRef(id=away_team_id),
                batting_order=list(range(200001, 200001 + order_size)),
            ),
        )
    )


@pytest.fixture()
def stub_fetchers(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Stub the 3 client fetchers. Returns call-log dict for assertions."""
    calls: dict[str, list] = {
        "schedule": [],
        "boxscore": [],
        "game_content": [],
    }

    _games: list[ScheduleGameWithProbables] = []
    _boxscores: dict[int, BoxscoreResponse] = {}
    _roof: dict[int, str | None] = {}

    def _fake_schedule(start, end) -> Iterator[ScheduleGameWithProbables]:
        calls["schedule"].append((start, end))
        yield from _games

    def _fake_boxscore(game_pk: int) -> BoxscoreResponse:
        calls["boxscore"].append(game_pk)
        return _boxscores.get(game_pk) or BoxscoreResponse()

    def _fake_game_content(game_pk: int) -> str | None:
        calls["game_content"].append(game_pk)
        return _roof.get(game_pk)

    monkeypatch.setattr(orchestrator, "fetch_schedule_with_probables", _fake_schedule)
    monkeypatch.setattr(orchestrator, "fetch_boxscore", _fake_boxscore)
    monkeypatch.setattr(orchestrator, "fetch_game_content", _fake_game_content)

    # Expose the mutable collections so tests can populate them.
    calls["_games"] = _games  # type: ignore[assignment]
    calls["_boxscores"] = _boxscores  # type: ignore[assignment]
    calls["_roof"] = _roof  # type: ignore[assignment]
    return calls


@pytest.mark.integration
def test_persist_daily_schedule_writes_rows(
    seeded_parks_teams: Engine, stub_fetchers: dict
) -> None:
    from datetime import date

    stub_fetchers["_games"].extend(
        [
            _make_game(game_pk=900001, venue_id=3313),  # Yankee Stadium
            _make_game(game_pk=900002, venue_id=17),  # Wrigley
        ]
    )
    stub_fetchers["_boxscores"][900001] = _make_boxscore(147, 117)
    stub_fetchers["_boxscores"][900002] = _make_boxscore(112, 143)
    stub_fetchers["_roof"][900001] = None
    stub_fetchers["_roof"][900002] = None

    written = persist_daily_schedule(date(2026, 4, 22), engine=seeded_parks_teams)
    assert written == 2

    with seeded_parks_teams.connect() as c:
        schedule_count = c.execute(
            text("SELECT COUNT(*) FROM daily_schedule WHERE game_pk IN (900001, 900002)")
        ).scalar_one()
        lineup_count = c.execute(
            text("SELECT COUNT(*) FROM projected_lineups WHERE game_pk IN (900001, 900002)")
        ).scalar_one()

    assert schedule_count == 2
    assert lineup_count == 2 * 2 * 9  # 2 games x 2 sides x 9 slots


@pytest.mark.integration
def test_persist_daily_schedule_is_idempotent(
    seeded_parks_teams: Engine, stub_fetchers: dict
) -> None:
    from datetime import date

    stub_fetchers["_games"].append(_make_game(game_pk=900101, venue_id=3313))
    stub_fetchers["_boxscores"][900101] = _make_boxscore(147, 117)
    stub_fetchers["_roof"][900101] = "closed"

    persist_daily_schedule(date(2026, 4, 22), engine=seeded_parks_teams)
    persist_daily_schedule(date(2026, 4, 22), engine=seeded_parks_teams)

    with seeded_parks_teams.connect() as c:
        schedule_count = c.execute(
            text("SELECT COUNT(*) FROM daily_schedule WHERE game_pk = 900101")
        ).scalar_one()
        lineup_count = c.execute(
            text("SELECT COUNT(*) FROM projected_lineups WHERE game_pk = 900101")
        ).scalar_one()
        roof = c.execute(
            text("SELECT roof_status FROM daily_schedule WHERE game_pk = 900101")
        ).scalar_one()

    assert schedule_count == 1
    assert lineup_count == 18
    assert roof == "closed"


@pytest.mark.integration
def test_persist_handles_doubleheaders(seeded_parks_teams: Engine, stub_fetchers: dict) -> None:
    from datetime import date

    # Two games, same teams + date, distinct game_pks.
    stub_fetchers["_games"].extend(
        [
            _make_game(
                game_pk=900201,
                home_team_id=147,
                away_team_id=117,
                venue_id=3313,
                game_start=datetime(2026, 4, 22, 17, 10, tzinfo=UTC),
            ),
            _make_game(
                game_pk=900202,
                home_team_id=147,
                away_team_id=117,
                venue_id=3313,
                game_start=datetime(2026, 4, 22, 23, 10, tzinfo=UTC),
            ),
        ]
    )
    stub_fetchers["_boxscores"][900201] = _make_boxscore(147, 117)
    stub_fetchers["_boxscores"][900202] = _make_boxscore(147, 117)

    written = persist_daily_schedule(date(2026, 4, 22), engine=seeded_parks_teams)
    assert written == 2

    with seeded_parks_teams.connect() as c:
        rows = (
            c.execute(
                text(
                    "SELECT game_pk FROM daily_schedule "
                    "WHERE game_pk IN (900201, 900202) ORDER BY game_pk"
                )
            )
            .scalars()
            .all()
        )
    assert list(rows) == [900201, 900202]


@pytest.mark.integration
def test_persist_tolerates_empty_boxscore(seeded_parks_teams: Engine, stub_fetchers: dict) -> None:
    """Lineups not yet posted (morning pull) -> schedule row still writes, 0 lineups."""
    from datetime import date

    stub_fetchers["_games"].append(_make_game(game_pk=900301, venue_id=3313))
    # Do NOT seed a boxscore -- stub returns empty BoxscoreResponse.

    written = persist_daily_schedule(date(2026, 4, 22), engine=seeded_parks_teams)
    assert written == 1

    with seeded_parks_teams.connect() as c:
        schedule_count = c.execute(
            text("SELECT COUNT(*) FROM daily_schedule WHERE game_pk = 900301")
        ).scalar_one()
        lineup_count = c.execute(
            text("SELECT COUNT(*) FROM projected_lineups WHERE game_pk = 900301")
        ).scalar_one()
    assert schedule_count == 1
    assert lineup_count == 0
