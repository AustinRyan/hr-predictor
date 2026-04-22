from collections.abc import Iterator

import pytest
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError
from src.core.db import get_engine
from src.core.redis_client import get_redis

_DOCKER_HINT = (
    "Could not reach {service}. These tests require docker-compose services. "
    "Run `docker-compose up -d` from the project root and try again."
)


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
