"""Tests for The Odds API client and HR prop normalizer."""

from __future__ import annotations

from datetime import UTC, datetime

from src.ingestion.prop_line_client import PropLineEventOdds, flatten_batter_home_run_odds
from src.ingestion.the_odds_api_client import TheOddsApiClient

SAMPLE_EVENT_ODDS = {
    "id": "toa_evt_123",
    "sport_key": "baseball_mlb",
    "sport_title": "MLB",
    "commence_time": "2026-05-13T23:05:00Z",
    "home_team": "New York Yankees",
    "away_team": "Boston Red Sox",
    "bookmakers": [
        {
            "key": "fanduel",
            "title": "FanDuel",
            "last_update": "2026-05-13T15:00:00Z",
            "markets": [
                {
                    "key": "batter_home_runs",
                    "last_update": "2026-05-13T15:01:00Z",
                    "outcomes": [
                        {
                            "name": "Over",
                            "description": "Aaron Judge",
                            "price": 650,
                            "point": 0.5,
                        },
                        {
                            "name": "Under",
                            "description": "Aaron Judge",
                            "price": -950,
                            "point": 0.5,
                        },
                    ],
                }
            ],
        }
    ],
}


def test_the_odds_api_client_uses_v4_host_and_retrying_session() -> None:
    client = TheOddsApiClient(api_key="test-key")
    retry_config = client._session.adapters["https://"].max_retries

    assert client._base_url == "https://api.the-odds-api.com/v4"
    assert retry_config.total == 3
    assert retry_config.connect == 3
    assert retry_config.read == 3
    assert retry_config.status == 3


def test_flatten_can_tag_rows_as_the_odds_api_provider() -> None:
    event = PropLineEventOdds.model_validate(SAMPLE_EVENT_ODDS)

    rows = flatten_batter_home_run_odds(
        event,
        provider="the_odds_api",
        fetched_at=datetime(2026, 5, 13, 15, 2, tzinfo=UTC),
    )

    assert len(rows) == 2
    over = next(r for r in rows if r.outcome_name == "Over")
    assert over.provider == "the_odds_api"
    assert over.event_id == "toa_evt_123"
    assert over.player_name == "Aaron Judge"
    assert over.price_american == 650
