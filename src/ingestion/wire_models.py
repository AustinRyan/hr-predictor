"""Pydantic models for external-API responses.

Every external API response is parsed into a model defined here before
touching the database layer (CLAUDE.md: "No raw dicts from external APIs.").
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class VenueLocation(BaseModel):
    """`location` subtree from MLB StatsAPI `/api/v1/venues?hydrate=location`."""

    model_config = ConfigDict(extra="ignore")

    city: str | None = None
    state: str | None = None
    state_abbrev: str | None = Field(default=None, alias="stateAbbrev")
    latitude: float | None = None
    longitude: float | None = None
    azimuth_angle: float | None = Field(default=None, alias="azimuthAngle")
    elevation: int | None = None
    country: str | None = None


class VenueCoordinates(BaseModel):
    model_config = ConfigDict(extra="ignore")

    latitude: float | None = None
    longitude: float | None = None


class Venue(BaseModel):
    """Single venue from MLB StatsAPI venues endpoint with location hydrated."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: int
    name: str
    active: bool | None = None
    season: str | None = None
    location: VenueLocation | None = None

    @property
    def latitude(self) -> float | None:
        loc = self.location
        if loc is None:
            return None
        return loc.latitude

    @property
    def longitude(self) -> float | None:
        loc = self.location
        if loc is None:
            return None
        return loc.longitude


class VenuesResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    venues: list[Venue] = Field(default_factory=list)


class TeamVenueRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str | None = None


class TeamLeagueRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str | None = None


class TeamDivisionRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str | None = None


class Team(BaseModel):
    """Single team from MLB StatsAPI `/api/v1/teams`."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: int
    name: str
    abbreviation: str | None = None
    venue: TeamVenueRef | None = None
    league: TeamLeagueRef | None = None
    division: TeamDivisionRef | None = None
    active: bool | None = None
    sport_id: int | None = Field(default=None, alias="sportId")


class TeamsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    teams: list[Team] = Field(default_factory=list)


class ScheduleTeamEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str | None = None


class ScheduleTeams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    away: dict | None = None
    home: dict | None = None


class ScheduleStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    abstract_game_state: str | None = Field(default=None, alias="abstractGameState")
    detailed_state: str | None = Field(default=None, alias="detailedState")


class ScheduleGame(BaseModel):
    """Single game entry from `/api/v1/schedule`."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    game_pk: int = Field(alias="gamePk")
    game_date: datetime = Field(alias="gameDate")
    official_date: date | None = Field(default=None, alias="officialDate")
    game_type: str | None = Field(default=None, alias="gameType")
    season: str | None = None
    status: ScheduleStatus | None = None
    teams: ScheduleTeams | None = None
    venue: TeamVenueRef | None = None
    day_night: str | None = Field(default=None, alias="dayNight")


class ScheduleDate(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    day: date | None = Field(default=None, alias="date")
    games: list[ScheduleGame] = Field(default_factory=list)


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dates: list[ScheduleDate] = Field(default_factory=list)

    def iter_games(self):
        for d in self.dates:
            yield from d.games
