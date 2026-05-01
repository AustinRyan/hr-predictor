"""Shared fixtures across the entire test suite.

`test_engine` + `clean_tables` + `seeded_parks_teams` live here so that
both `tests/ingestion/` and `tests/features/` can share a single
session-scoped `hrp_test` DB (creating it twice races under `DROP
DATABASE` when multiple conftests each register their own copy).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from src.core.db import get_engine
from src.core.redis_client import get_redis

_DOCKER_HINT = (
    "Could not reach {service}. These tests require docker-compose services. "
    "Run `docker-compose up -d` from the project root and try again."
)

_PRIMARY_URL = "postgresql+psycopg://hrp:hrp@localhost:5432/hrp"
_TEST_DB_NAME = "hrp_test"
_TEST_URL = f"postgresql+psycopg://hrp:hrp@localhost:5432/{_TEST_DB_NAME}"


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.fail(_DOCKER_HINT.format(service="Postgres") + f" Underlying error: {exc}")
    yield engine


@pytest.fixture(scope="session")
def redis_client() -> Iterator[Redis]:
    client = get_redis()
    try:
        client.ping()
    except RedisConnectionError as exc:
        pytest.fail(_DOCKER_HINT.format(service="Redis") + f" Underlying error: {exc}")
    yield client


def _admin_engine() -> Engine:
    # postgres superuser conn via the default postgres DB — used to
    # CREATE/DROP the test DB outside any transaction.
    return create_engine(
        "postgresql+psycopg://hrp:hrp@localhost:5432/postgres",
        isolation_level="AUTOCOMMIT",
    )


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    admin = _admin_engine()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {_TEST_DB_NAME}"))
        c.execute(text(f"CREATE DATABASE {_TEST_DB_NAME}"))
    admin.dispose()

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", _TEST_URL)
    # Route env.py onto the test URL without touching Settings.
    import os

    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _TEST_URL
    try:
        # Ensure Settings reload picks up the override.
        from src.core.config import get_settings
        from src.core.db import _get_sessionmaker, get_engine

        get_settings.cache_clear()
        get_engine.cache_clear()
        _get_sessionmaker.cache_clear()

        command.upgrade(cfg, "head")

        engine = create_engine(_TEST_URL, future=True)
        yield engine
        engine.dispose()
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
        from src.core.config import get_settings
        from src.core.db import _get_sessionmaker, get_engine

        get_settings.cache_clear()
        get_engine.cache_clear()
        _get_sessionmaker.cache_clear()

        admin = _admin_engine()
        with admin.connect() as c:
            # Kick any still-open sessions so DROP can proceed.
            c.execute(
                text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :db"),
                {"db": _TEST_DB_NAME},
            )
            c.execute(text(f"DROP DATABASE IF EXISTS {_TEST_DB_NAME}"))
        admin.dispose()


@pytest.fixture()
def clean_tables(test_engine: Engine) -> Iterator[None]:
    """Truncate ingestion + feature tables so each test starts clean."""
    with test_engine.begin() as c:
        c.execute(
            text(
                "TRUNCATE TABLE odds_snapshots, predictions, matchup_features, statcast_pitches, "
                "projected_lineups, weather_forecasts, park_factors, daily_schedule, "
                "games, players, teams, parks, ingestion_state "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest.fixture()
def seeded_parks_teams(test_engine: Engine, clean_tables) -> Engine:
    """Pre-seed parks + teams with synthetic values.

    Stands in for the production prerequisite: teams + parks must be
    seeded before backfill can write games, since games FK both.
    """
    from src.core.models import Park, Team

    Session_ = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with Session_() as s:
        # MLB team_ids: 108-121 (AL/NL split 1) + 133-147 + 158 (MIL).
        team_ids = list(range(108, 122)) + list(range(133, 148)) + [158]
        s.add_all(
            [
                Park(park_id=pid, name=f"park_{pid}")
                for pid in (
                    3313,
                    3,
                    19,
                    17,
                    22,
                    2889,
                    5325,
                    4705,
                    12,
                    1,
                    2,
                    4,
                    5,
                    7,
                    10,
                    14,
                    15,
                    31,
                    32,
                    680,
                    2392,
                    2394,
                    2395,
                    2523,
                    2529,
                    2602,
                    2680,
                    2681,
                    3289,
                    3309,
                    3312,
                    4169,
                )
            ]
        )
        s.add_all([Team(team_id=tid, abbr=f"T{tid}", name=f"Team {tid}") for tid in team_ids])
        s.commit()
    return test_engine
