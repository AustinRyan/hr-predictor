"""Health endpoint tests."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
@pytest.mark.integration
async def test_health_returns_200_when_all_ok(client) -> None:
    r = await client.get("/health")
    assert r.status_code in (200, 503)  # 503 if nothing is up locally
    body = r.json()
    assert "status" in body
    assert "postgres" in body
    assert "redis" in body
    assert "model_version" in body


@pytest.mark.asyncio
@pytest.mark.integration
async def test_health_body_shape(client) -> None:
    r = await client.get("/health")
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert body["postgres"] in ("ok", "down")
    assert body["redis"] in ("ok", "down")
