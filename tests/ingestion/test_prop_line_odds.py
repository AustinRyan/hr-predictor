"""Tests for PropLine odds persistence."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Engine, text
from src.ingestion.prop_line_client import PropLineEvent, PropLineEventOdds
from src.ingestion.prop_line_odds import persist_mlb_batter_hr_odds


class FakePropLineClient:
    def __init__(self, event_odds: PropLineEventOdds) -> None:
        self.event_odds = event_odds

    def fetch_events(self, sport_key: str) -> list[PropLineEvent]:
        assert sport_key == "baseball_mlb"
        return [
            PropLineEvent(
                event_id=self.event_odds.event_id,
                sport_key=self.event_odds.sport_key,
                commence_time=self.event_odds.commence_time,
                home_team=self.event_odds.home_team,
                away_team=self.event_odds.away_team,
            )
        ]

    def fetch_event_odds(
        self,
        *,
        sport_key: str,
        event_id: str,
        markets: tuple[str, ...],
    ) -> PropLineEventOdds:
        assert sport_key == "baseball_mlb"
        assert event_id == self.event_odds.event_id
        assert markets == ("batter_home_runs",)
        return self.event_odds


def _seed_game(test_engine: Engine) -> None:
    with test_engine.begin() as c:
        c.execute(text("INSERT INTO parks (park_id, name) VALUES (3313, 'Yankee Stadium')"))
        c.execute(
            text(
                "INSERT INTO teams (team_id, abbr, name) VALUES "
                "(147, 'NYY', 'New York Yankees'), "
                "(111, 'BOS', 'Boston Red Sox')"
            )
        )
        c.execute(
            text(
                "INSERT INTO players (mlbam_id, full_name, first_name, last_name, active) "
                "VALUES (592450, 'Aaron Judge', 'Aaron', 'Judge', true)"
            )
        )
        c.execute(
            text(
                "INSERT INTO daily_schedule "
                "(game_pk, game_date, home_team_id, away_team_id, venue_id, game_start_utc, status) "
                "VALUES "
                "(999001, '2026-05-01', 147, 111, 3313, '2026-05-01T23:05:00Z', 'Scheduled')"
            )
        )


def _event_odds() -> PropLineEventOdds:
    return PropLineEventOdds.model_validate(
        {
            "id": "evt_123",
            "sport_key": "baseball_mlb",
            "commence_time": "2026-05-01T23:05:00Z",
            "home_team": "New York Yankees",
            "away_team": "Boston Red Sox",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {
                            "key": "batter_home_runs",
                            "last_update": "2026-05-01T16:01:00Z",
                            "outcomes": [
                                {
                                    "name": "Over",
                                    "description": "Aaron Judge",
                                    "price": 700,
                                    "point": 0.5,
                                },
                                {
                                    "name": "Under",
                                    "description": "Aaron Judge",
                                    "price": -1000,
                                    "point": 0.5,
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )


def test_persist_mlb_batter_hr_odds_upserts_and_matches_game_player(
    test_engine: Engine,
    clean_tables,
) -> None:
    _seed_game(test_engine)
    client = FakePropLineClient(_event_odds())

    report1 = persist_mlb_batter_hr_odds(
        date(2026, 5, 1),
        engine=test_engine,
        client=client,
        fetched_at=datetime(2026, 5, 1, 16, 2, tzinfo=UTC),
    )
    report2 = persist_mlb_batter_hr_odds(
        date(2026, 5, 1),
        engine=test_engine,
        client=client,
        fetched_at=datetime(2026, 5, 1, 16, 2, tzinfo=UTC),
    )

    assert report1.events_seen == 1
    assert report1.rows_written == 2
    assert report2.rows_written == 2
    with test_engine.connect() as c:
        rows = (
            c.execute(
                text(
                    "SELECT game_pk, batter_id, outcome_name, price_american, implied_probability "
                    "FROM odds_snapshots WHERE outcome_name = 'Over'"
                )
            )
            .mappings()
            .all()
        )
        count = c.execute(text("SELECT COUNT(*) FROM odds_snapshots")).scalar_one()
    assert count == 2
    assert rows[0]["game_pk"] == 999001
    assert rows[0]["batter_id"] == 592450
    assert rows[0]["outcome_name"] == "Over"
    assert rows[0]["price_american"] == 700
    assert float(rows[0]["implied_probability"]) == 100 / 800
