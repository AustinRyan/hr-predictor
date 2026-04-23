"""Health endpoint: Postgres + Redis connectivity + model load status."""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from src.api.dependencies import _get_session_factory, get_redis

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    status: str
    postgres: str
    redis: str
    model_version: str | None


@router.get("/health", response_model=HealthStatus)
def health(request: Request) -> JSONResponse:
    pg_ok = True
    try:
        session = _get_session_factory()()
        try:
            session.execute(text("SELECT 1"))
        finally:
            session.close()
    except OperationalError:
        pg_ok = False

    redis_ok = True
    try:
        get_redis().ping()
    except RedisError:
        redis_ok = False

    loaded = getattr(request.app.state, "loaded_model", None)
    model_version = loaded.version if loaded else None

    body = HealthStatus(
        status="ok" if (pg_ok and redis_ok) else "degraded",
        postgres="ok" if pg_ok else "down",
        redis="ok" if redis_ok else "down",
        model_version=model_version,
    )
    code = status.HTTP_200_OK if (pg_ok and redis_ok) else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=body.model_dump(), status_code=code)
