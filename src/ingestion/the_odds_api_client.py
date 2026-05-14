"""Typed client for The Odds API v4 MLB player props."""

from __future__ import annotations

from typing import Any

import requests

from src.core.config import get_settings
from src.ingestion.prop_line_client import (
    PropLineEvent,
    PropLineEventOdds,
    _build_retrying_session,
)

_BATTER_HR_MARKET = "batter_home_runs"


class TheOddsApiClient:
    """Small requests client for The Odds API v4.

    The Odds API and PropLine use the same event/bookmaker/market payload
    shape for this endpoint, so the existing Pydantic models are reused.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        regions: str | None = None,
        timeout_seconds: float = 20.0,
        session: requests.Session | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.the_odds_api_key
        self._base_url = (base_url or settings.the_odds_api_base_url).rstrip("/")
        self._regions = regions or settings.the_odds_api_regions
        self._timeout_seconds = timeout_seconds
        self._session = session or _build_retrying_session()

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        if not self._api_key:
            raise RuntimeError("THE_ODDS_API_KEY is not configured")
        merged = dict(params or {})
        merged["apiKey"] = self._api_key
        response = self._session.get(
            f"{self._base_url}{path}",
            params=merged,
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def fetch_sports(self) -> list[dict[str, Any]]:
        payload = self._get("/sports")
        if not isinstance(payload, list):
            raise TypeError("The Odds API /sports response must be a list")
        return payload

    def fetch_events(self, sport_key: str) -> list[PropLineEvent]:
        payload = self._get(f"/sports/{sport_key}/events")
        if not isinstance(payload, list):
            raise TypeError("The Odds API events response must be a list")
        return [PropLineEvent.model_validate(item) for item in payload]

    def fetch_event_odds(
        self,
        *,
        sport_key: str,
        event_id: str,
        markets: tuple[str, ...] = (_BATTER_HR_MARKET,),
    ) -> PropLineEventOdds:
        payload = self._get(
            f"/sports/{sport_key}/events/{event_id}/odds",
            {
                "regions": self._regions,
                "markets": ",".join(markets),
                "oddsFormat": "american",
            },
        )
        return PropLineEventOdds.model_validate(payload)
