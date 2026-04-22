import uuid

from redis import Redis
from sqlalchemy import Engine, text
from src.core.config import Settings, get_settings


def test_settings_loads_from_env() -> None:
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.database_url.startswith("postgresql"), settings.database_url
    assert settings.redis_url.startswith("redis://"), settings.redis_url
    assert settings.log_level


def test_postgres_select_one(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        result = conn.execute(text("SELECT 1 AS one")).scalar_one()
    assert result == 1


def test_redis_set_get_roundtrip(redis_client: Redis) -> None:
    key = f"hrp:test:{uuid.uuid4()}"
    value = "pong"
    try:
        assert redis_client.set(key, value) is True
        fetched = redis_client.get(key)
        assert fetched == value
    finally:
        redis_client.delete(key)
