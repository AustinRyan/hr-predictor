from functools import lru_cache

from redis import Redis

from src.core.config import get_settings


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    """Return a process-wide cached Redis client."""
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)
