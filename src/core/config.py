from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://hrp:hrp@localhost:5432/hrp",
        description="SQLAlchemy URL for Postgres.",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL.",
    )
    log_level: str = Field(default="INFO", description="Root logger level.")
    prop_line_api_key: str | None = Field(
        default=None,
        description="PropLine API key for sportsbook player prop odds.",
    )
    prop_line_base_url: str = Field(
        default="https://api.prop-line.com/v1",
        description="Base URL for PropLine's The-Odds-API-compatible endpoints.",
    )
    the_odds_api_key: str | None = Field(
        default=None,
        description="The Odds API key for sportsbook player prop odds.",
    )
    the_odds_api_base_url: str = Field(
        default="https://api.the-odds-api.com/v4",
        description="Base URL for The Odds API v4 endpoints.",
    )
    the_odds_api_regions: str = Field(
        default="us",
        description="Comma-separated The Odds API regions to request.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()
