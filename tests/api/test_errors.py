"""Error-response consistency tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from redis.exceptions import RedisError
from sqlalchemy.exc import OperationalError


@pytest.mark.asyncio
@pytest.mark.integration
async def test_404_body_shape(client) -> None:
    """404 responses should have consistent error body shape."""
    r = await client.get("/matchup/0/0")  # guaranteed no matchup
    assert r.status_code == 404
    body = r.json()
    assert "error" in body


@pytest.mark.asyncio
@pytest.mark.integration
async def test_422_validation_body_shape(client) -> None:
    """422 validation errors should have error=validation_error + detail."""
    r = await client.get("/picks/today?limit=0")  # ge=1 violates
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error"
    assert "detail" in body


@pytest.mark.asyncio
@pytest.mark.integration
async def test_422_on_invalid_literal(client) -> None:
    """422 on invalid Literal value."""
    r = await client.get("/picks/today?sort=nonsense")
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_health_503_when_postgres_down(client) -> None:
    """Simulate Postgres failure via the session_factory path. The health endpoint
    catches OperationalError and reports pg=down + 503."""

    class _FailingSession:
        def execute(self, *a, **kw):
            raise OperationalError("simulated", None, Exception("db down"))

        def close(self):
            pass

    class _FailingFactory:
        def __call__(self):
            return _FailingSession()

    with patch("src.api.routers.health._get_session_factory", return_value=_FailingFactory()):
        r = await client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["postgres"] == "down"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_health_503_when_redis_down(client) -> None:
    """Simulate Redis failure. The health endpoint catches RedisError and
    reports redis=down + 503."""

    class _BadRedis:
        def ping(self):
            raise RedisError("simulated redis down")

    with patch("src.api.routers.health.get_redis", return_value=_BadRedis()):
        r = await client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["redis"] == "down"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_health_both_up_returns_200(client) -> None:
    """When both Postgres and Redis are up, /health returns 200."""
    r = await client.get("/health")
    # Postgres + Redis should both be up in dev
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["postgres"] == "ok"
    assert body["redis"] == "ok"
