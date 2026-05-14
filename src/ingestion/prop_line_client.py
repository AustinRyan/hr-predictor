"""Typed PropLine client for MLB player-prop odds."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

import requests
from pydantic import BaseModel, ConfigDict, Field
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.core.config import get_settings
from src.models.odds import american_to_implied_probability

_BATTER_HR_MARKET = "batter_home_runs"
_TRANSIENT_STATUS_CODES = (429, 500, 502, 503, 504)
_GET_METHODS = frozenset({"GET"})
_HOME_RUN_LADDER_RE = re.compile(r"^\s*(\d+)\+\s+home runs?\s*$", re.IGNORECASE)


def _build_retrying_session() -> requests.Session:
    retry_config = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=_TRANSIENT_STATUS_CODES,
        allowed_methods=_GET_METHODS,
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry_config)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class PropLineEvent(BaseModel):
    """Event row returned by PropLine's sport events endpoint."""

    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    event_id: str = Field(alias="id")
    sport_key: str
    commence_time: datetime
    home_team: str
    away_team: str


class PropLineOutcome(BaseModel):
    """One sportsbook market outcome."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str
    price: int
    description: str | None = None
    point: float | None = None

    @property
    def player_name(self) -> str:
        return (self.description or self.name).strip()

    @property
    def outcome_name(self) -> str:
        side_names = {"over", "under", "yes", "no"}
        if self.name.strip().lower() in side_names:
            return self.name.strip().title()
        return "Yes"


class PropLineMarket(BaseModel):
    """Bookmaker market payload."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    key: str
    outcomes: list[PropLineOutcome] = Field(default_factory=list)
    last_update: datetime | None = None


class PropLineBookmaker(BaseModel):
    """Bookmaker payload nested under an event odds response."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    key: str
    title: str
    markets: list[PropLineMarket] = Field(default_factory=list)
    last_update: datetime | None = None


class PropLineEventOdds(PropLineEvent):
    """Full odds response for one event."""

    bookmakers: list[PropLineBookmaker] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FlattenedPropOdds:
    """Normalized sportsbook outcome before DB matching/enrichment."""

    provider: str
    sport_key: str
    event_id: str
    game_date: datetime
    commence_time: datetime
    home_team: str
    away_team: str
    bookmaker_key: str
    bookmaker_title: str
    market_key: str
    outcome_name: str
    player_name: str
    price_american: int
    point: float | None
    implied_probability: float
    no_vig_probability: float | None
    market_last_update: datetime | None
    raw_outcome: dict[str, Any]


class PropLineClient:
    """Small requests-based client for the PropLine odds API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 20.0,
        session: requests.Session | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.prop_line_api_key
        self._base_url = (base_url or settings.prop_line_base_url).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._session = session or _build_retrying_session()

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        if not self._api_key:
            raise RuntimeError("PROP_LINE_API_KEY is not configured")
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
            raise TypeError("PropLine /sports response must be a list")
        return payload

    def fetch_events(self, sport_key: str) -> list[PropLineEvent]:
        payload = self._get(f"/sports/{sport_key}/events")
        if not isinstance(payload, list):
            raise TypeError("PropLine events response must be a list")
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
                "regions": "us",
                "markets": ",".join(markets),
                "oddsFormat": "american",
            },
        )
        return PropLineEventOdds.model_validate(payload)


def _market_last_update(book: PropLineBookmaker, market: PropLineMarket) -> datetime | None:
    return market.last_update or book.last_update


def _no_vig_probabilities(
    rows: list[FlattenedPropOdds],
) -> dict[tuple[str, str, str, float | None], float]:
    grouped: dict[tuple[str, str, str, float | None], list[FlattenedPropOdds]] = {}
    for row in rows:
        key = (row.bookmaker_key, row.market_key, row.player_name, row.point)
        grouped.setdefault(key, []).append(row)

    no_vig: dict[tuple[str, str, str, float | None], float] = {}
    for key, group in grouped.items():
        names = {row.outcome_name.lower() for row in group}
        if not {"over", "under"} <= names:
            continue
        total = sum(row.implied_probability for row in group)
        if total <= 0:
            continue
        for row in group:
            no_vig[(key[0], key[1], row.outcome_name, key[2], key[3])] = (
                row.implied_probability / total
            )
    return no_vig


def _is_primary_batter_home_run_outcome(outcome: PropLineOutcome) -> bool:
    """Return True only for the 1+ HR market, excluding alternate HR ladders."""
    ladder = _HOME_RUN_LADDER_RE.match(outcome.name)
    if ladder is not None:
        return int(ladder.group(1)) == 1
    if outcome.point is not None and abs(float(outcome.point) - 0.5) > 1e-9:
        return False
    return True


def flatten_batter_home_run_odds(
    event: PropLineEventOdds,
    *,
    provider: str = "prop_line",
    fetched_at: datetime | None = None,
) -> list[FlattenedPropOdds]:
    """Flatten one event response to home-run prop outcomes."""
    _ = fetched_at or datetime.now(UTC)
    rows: list[FlattenedPropOdds] = []
    for book in event.bookmakers:
        for market in book.markets:
            if market.key != _BATTER_HR_MARKET:
                continue
            for outcome in market.outcomes:
                if not _is_primary_batter_home_run_outcome(outcome):
                    continue
                rows.append(
                    FlattenedPropOdds(
                        provider=provider,
                        sport_key=event.sport_key,
                        event_id=event.event_id,
                        game_date=event.commence_time,
                        commence_time=event.commence_time,
                        home_team=event.home_team,
                        away_team=event.away_team,
                        bookmaker_key=book.key,
                        bookmaker_title=book.title,
                        market_key=market.key,
                        outcome_name=outcome.outcome_name,
                        player_name=outcome.player_name,
                        price_american=outcome.price,
                        point=outcome.point,
                        implied_probability=american_to_implied_probability(outcome.price),
                        no_vig_probability=None,
                        market_last_update=_market_last_update(book, market),
                        raw_outcome=outcome.model_dump(exclude_none=True),
                    )
                )

    no_vig = _no_vig_probabilities(rows)
    return [
        replace(
            row,
            no_vig_probability=no_vig.get(
                (
                    row.bookmaker_key,
                    row.market_key,
                    row.outcome_name,
                    row.player_name,
                    row.point,
                )
            ),
        )
        for row in rows
    ]
