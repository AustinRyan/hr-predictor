"""Pydantic models for external-API responses.

Every external API response is parsed into a model defined here before
touching the database layer (CLAUDE.md: "No raw dicts from external APIs.").
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class VenueDefaultCoordinates(BaseModel):
    """`location.defaultCoordinates` subtree from `/api/v1/venues?hydrate=location`."""

    model_config = ConfigDict(extra="ignore")

    latitude: float | None = None
    longitude: float | None = None


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
    default_coordinates: VenueDefaultCoordinates | None = Field(
        default=None, alias="defaultCoordinates"
    )


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
        if loc.default_coordinates is not None and loc.default_coordinates.latitude is not None:
            return loc.default_coordinates.latitude
        return loc.latitude

    @property
    def longitude(self) -> float | None:
        loc = self.location
        if loc is None:
            return None
        if loc.default_coordinates is not None and loc.default_coordinates.longitude is not None:
            return loc.default_coordinates.longitude
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


# -------- Schedule with probable pitchers --------


class ProbablePitcherRef(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: int | None = None
    full_name: str | None = Field(default=None, alias="fullName")


class ScheduleTeamSideWithProbable(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    team: TeamVenueRef | None = None
    probable_pitcher: ProbablePitcherRef | None = Field(default=None, alias="probablePitcher")


class ScheduleTeamsWithProbables(BaseModel):
    model_config = ConfigDict(extra="ignore")

    home: ScheduleTeamSideWithProbable | None = None
    away: ScheduleTeamSideWithProbable | None = None


class ScheduleGameWithProbables(BaseModel):
    """Schedule entry hydrated with probablePitcher + linescore."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    game_pk: int = Field(alias="gamePk")
    game_date: datetime = Field(alias="gameDate")
    official_date: date | None = Field(default=None, alias="officialDate")
    game_type: str | None = Field(default=None, alias="gameType")
    season: str | None = None
    status: ScheduleStatus | None = None
    teams: ScheduleTeamsWithProbables | None = None
    venue: TeamVenueRef | None = None
    day_night: str | None = Field(default=None, alias="dayNight")

    @property
    def home_team_id(self) -> int | None:
        return (
            self.teams.home.team.id
            if (self.teams and self.teams.home and self.teams.home.team)
            else None
        )

    @property
    def away_team_id(self) -> int | None:
        return (
            self.teams.away.team.id
            if (self.teams and self.teams.away and self.teams.away.team)
            else None
        )

    @property
    def venue_id(self) -> int | None:
        return self.venue.id if self.venue else None

    @property
    def home_probable_pitcher_id(self) -> int | None:
        side = self.teams.home if self.teams else None
        if side is None or side.probable_pitcher is None:
            return None
        return side.probable_pitcher.id

    @property
    def away_probable_pitcher_id(self) -> int | None:
        side = self.teams.away if self.teams else None
        if side is None or side.probable_pitcher is None:
            return None
        return side.probable_pitcher.id


class ScheduleWithProbablesResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dates: list[dict] = Field(default_factory=list)

    def iter_games(self):
        for d in self.dates:
            for raw_game in d.get("games", []):
                yield ScheduleGameWithProbables.model_validate(raw_game)


class ProbablePitchers(BaseModel):
    """Convenience tuple: (home_id, away_id) for a single game."""

    model_config = ConfigDict(extra="ignore")

    home_pitcher_id: int | None = None
    away_pitcher_id: int | None = None


# -------- Boxscore (lineups) --------


class BoxscoreTeamRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None


class BoxscoreTeamSide(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    team: BoxscoreTeamRef = Field(default_factory=BoxscoreTeamRef)
    batting_order: list[int] = Field(default_factory=list, alias="battingOrder")


class BoxscoreTeams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    home: BoxscoreTeamSide = Field(default_factory=BoxscoreTeamSide)
    away: BoxscoreTeamSide = Field(default_factory=BoxscoreTeamSide)


class BoxscoreResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    teams: BoxscoreTeams = Field(default_factory=BoxscoreTeams)


# -------- Open-Meteo forecast --------


class OpenMeteoHourly(BaseModel):
    """Parallel arrays keyed by hour; length matches `time`."""

    model_config = ConfigDict(extra="ignore")

    time: list[str] = Field(default_factory=list)
    temperature_2m: list[float] = Field(default_factory=list)
    apparent_temperature: list[float] = Field(default_factory=list)
    relative_humidity_2m: list[float] = Field(default_factory=list)
    surface_pressure: list[float] = Field(default_factory=list)
    wind_speed_10m: list[float] = Field(default_factory=list)
    wind_direction_10m: list[float] = Field(default_factory=list)
    precipitation_probability: list[float] = Field(default_factory=list)
    cloud_cover: list[float] = Field(default_factory=list)


class OpenMeteoForecastResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    latitude: float
    longitude: float
    timezone: str | None = None
    hourly: OpenMeteoHourly = Field(default_factory=OpenMeteoHourly)


# -------- Feed/live (game content) --------


class FeedLiveWeather(BaseModel):
    """Subset of `gameData.weather` from `/api/v1.1/game/{pk}/feed/live`."""

    model_config = ConfigDict(extra="ignore")

    condition: str | None = None


class FeedLiveVenue(BaseModel):
    """Subset of `gameData.venue` from `/api/v1.1/game/{pk}/feed/live`."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    roof_type: str | None = Field(default=None, alias="roofType")


class FeedLiveGameData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    weather: FeedLiveWeather = Field(default_factory=FeedLiveWeather)
    venue: FeedLiveVenue = Field(default_factory=FeedLiveVenue)


class FeedLiveResponse(BaseModel):
    """Root of `/api/v1.1/game/{pk}/feed/live` (only the subset we consume)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    game_data: FeedLiveGameData = Field(default_factory=FeedLiveGameData, alias="gameData")
