"""Unit tests for Phase 2 Pydantic wire models."""

from __future__ import annotations

import pytest
from src.ingestion.wire_models import (
    BoxscoreResponse,
    OpenMeteoForecastResponse,
    ScheduleGameWithProbables,
)


def test_schedule_game_parses_probable_pitcher_ids() -> None:
    raw = {
        "gamePk": 745999,
        "gameDate": "2026-04-22T23:10:00Z",
        "officialDate": "2026-04-22",
        "teams": {
            "home": {
                "team": {"id": 147, "name": "Yankees"},
                "probablePitcher": {"id": 656756, "fullName": "Carlos Rodón"},
            },
            "away": {
                "team": {"id": 117, "name": "Astros"},
                "probablePitcher": {"id": 543037, "fullName": "Gerrit Cole"},
            },
        },
        "venue": {"id": 3313, "name": "Yankee Stadium"},
        "status": {"abstractGameState": "Preview", "detailedState": "Scheduled"},
    }
    g = ScheduleGameWithProbables.model_validate(raw)
    assert g.game_pk == 745999
    assert g.home_probable_pitcher_id == 656756
    assert g.away_probable_pitcher_id == 543037
    assert g.home_team_id == 147
    assert g.away_team_id == 117
    assert g.venue_id == 3313


def test_schedule_game_tolerates_missing_probables() -> None:
    raw = {
        "gamePk": 745998,
        "gameDate": "2026-04-22T23:10:00Z",
        "teams": {
            "home": {"team": {"id": 147}},
            "away": {"team": {"id": 117}},
        },
        "venue": {"id": 3313},
        "status": {"detailedState": "Scheduled"},
    }
    g = ScheduleGameWithProbables.model_validate(raw)
    assert g.home_probable_pitcher_id is None
    assert g.away_probable_pitcher_id is None


def test_boxscore_response_extracts_batting_order() -> None:
    raw = {
        "teams": {
            "home": {
                "team": {"id": 147},
                "battingOrder": [
                    592450,
                    624413,
                    519317,
                    518617,
                    457763,
                    500871,
                    664761,
                    571697,
                    593428,
                ],
                "players": {
                    "ID592450": {"person": {"id": 592450}, "battingOrder": "100"},
                    "ID624413": {"person": {"id": 624413}, "battingOrder": "200"},
                },
            },
            "away": {
                "team": {"id": 117},
                "battingOrder": [514888, 608324],
                "players": {},
            },
        }
    }
    bx = BoxscoreResponse.model_validate(raw)
    assert bx.teams.home.team.id == 147
    assert bx.teams.home.batting_order == [
        592450,
        624413,
        519317,
        518617,
        457763,
        500871,
        664761,
        571697,
        593428,
    ]
    assert bx.teams.away.batting_order == [514888, 608324]


def test_openmeteo_forecast_parses_hourly_arrays() -> None:
    raw = {
        "latitude": 39.75,
        "longitude": -104.99,
        "timezone": "GMT",
        "hourly": {
            "time": ["2026-04-22T23:00", "2026-04-23T00:00"],
            "temperature_2m": [18.5, 17.2],
            "apparent_temperature": [17.0, 16.1],
            "relative_humidity_2m": [55.0, 60.0],
            "surface_pressure": [1013.2, 1013.0],
            "wind_speed_10m": [4.5, 4.0],
            "wind_direction_10m": [270.0, 265.0],
            "precipitation_probability": [10.0, 15.0],
            "cloud_cover": [30.0, 40.0],
        },
    }
    f = OpenMeteoForecastResponse.model_validate(raw)
    assert len(f.hourly.time) == 2
    assert f.hourly.temperature_2m == [18.5, 17.2]
    assert f.hourly.wind_direction_10m == [270.0, 265.0]


def test_feed_live_response_parses_weather_and_venue_roof() -> None:
    from src.ingestion.wire_models import FeedLiveResponse

    raw = {
        "gameData": {
            "weather": {"condition": "Roof Closed", "temp": "72", "wind": "0 mph, Calm"},
            "venue": {"id": 15, "name": "Chase Field", "roofType": "Retractable"},
            "datetime": {"dateTime": "2026-04-22T23:10:00Z"},  # extra ignored
        }
    }
    parsed = FeedLiveResponse.model_validate(raw)
    assert parsed.game_data.weather.condition == "Roof Closed"
    assert parsed.game_data.venue.roof_type == "Retractable"


def test_feed_live_response_tolerates_missing_subtrees() -> None:
    from src.ingestion.wire_models import FeedLiveResponse

    parsed = FeedLiveResponse.model_validate({})
    assert parsed.game_data.weather.condition is None
    assert parsed.game_data.venue.roof_type is None


def test_venue_latitude_prefers_default_coordinates() -> None:
    from src.ingestion.wire_models import Venue

    raw = {
        "id": 19,
        "name": "Coors Field",
        "location": {
            "city": "Denver",
            "state": "Colorado",
            "defaultCoordinates": {"latitude": 39.7559, "longitude": -104.9942},
            "azimuthAngle": 4.0,
            "elevation": 5190,
        },
    }
    v = Venue.model_validate(raw)
    assert v.latitude == pytest.approx(39.7559)
    assert v.longitude == pytest.approx(-104.9942)
    # Still exposes orientation and elevation via the flat fields
    assert v.location.azimuth_angle == 4.0
    assert v.location.elevation == 5190


def test_venue_latitude_falls_back_to_flat_fields() -> None:
    """If a future API shape emits lat/lon at the location root, prefer those when no defaultCoordinates."""
    from src.ingestion.wire_models import Venue

    raw = {
        "id": 99,
        "name": "Hypothetical Park",
        "location": {"latitude": 40.0, "longitude": -75.0},
    }
    v = Venue.model_validate(raw)
    assert v.latitude == 40.0
    assert v.longitude == -75.0
