"""API test fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from asgi_lifespan import LifespanManager
from src.api.main import create_app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Yields an AsyncClient bound to a fresh app with lifespan managed."""
    app = create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
