"""Tests for the PropLine odds client parser/normalizer."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from src.ingestion.prop_line_client import PropLineEventOdds, flatten_batter_home_run_odds

SAMPLE_EVENT_ODDS = {
    "id": "evt_123",
    "sport_key": "baseball_mlb",
    "sport_title": "MLB",
    "commence_time": "2026-05-01T23:05:00Z",
    "home_team": "New York Yankees",
    "away_team": "Boston Red Sox",
    "bookmakers": [
        {
            "key": "draftkings",
            "title": "DraftKings",
            "last_update": "2026-05-01T16:00:00Z",
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


def test_event_odds_parser_accepts_the_odds_api_style_payload() -> None:
    event = PropLineEventOdds.model_validate(SAMPLE_EVENT_ODDS)

    assert event.event_id == "evt_123"
    assert event.commence_time == datetime(2026, 5, 1, 23, 5, tzinfo=UTC)
    assert event.bookmakers[0].markets[0].outcomes[0].player_name == "Aaron Judge"


def test_flatten_batter_home_run_odds_computes_implied_and_no_vig() -> None:
    event = PropLineEventOdds.model_validate(SAMPLE_EVENT_ODDS)

    rows = flatten_batter_home_run_odds(event, fetched_at=datetime(2026, 5, 1, 16, 2, tzinfo=UTC))

    assert len(rows) == 2
    over = next(r for r in rows if r.outcome_name == "Over")
    under = next(r for r in rows if r.outcome_name == "Under")
    assert over.player_name == "Aaron Judge"
    assert over.price_american == 700
    assert over.implied_probability == pytest.approx(0.125)
    assert under.implied_probability == pytest.approx(1000 / 1100)
    assert over.no_vig_probability == pytest.approx(0.125 / (0.125 + 1000 / 1100))
    assert under.no_vig_probability == pytest.approx((1000 / 1100) / (0.125 + 1000 / 1100))


def test_flatten_ignores_non_home_run_markets() -> None:
    payload = dict(SAMPLE_EVENT_ODDS)
    payload["bookmakers"] = [
        {
            "key": "draftkings",
            "title": "DraftKings",
            "markets": [{"key": "h2h", "outcomes": [{"name": "Yankees", "price": -120}]}],
        }
    ]
    event = PropLineEventOdds.model_validate(payload)

    assert flatten_batter_home_run_odds(event) == []


def test_flatten_normalizes_player_named_yes_market() -> None:
    payload = dict(SAMPLE_EVENT_ODDS)
    payload["bookmakers"] = [
        {
            "key": "betrivers",
            "title": "BetRivers",
            "markets": [
                {
                    "key": "batter_home_runs",
                    "last_update": "2026-05-01T16:01:00Z",
                    "outcomes": [{"name": "Aaron Judge", "price": 700}],
                }
            ],
        }
    ]
    event = PropLineEventOdds.model_validate(payload)

    rows = flatten_batter_home_run_odds(event)

    assert len(rows) == 1
    assert rows[0].outcome_name == "Yes"
    assert rows[0].player_name == "Aaron Judge"
    assert rows[0].point is None
