"""FastAPI dependency-injection helpers: DB session, Redis, model, calibrator."""

from __future__ import annotations

import logging
from collections.abc import Generator

from fastapi import HTTPException, Request, status
from redis import Redis
from sklearn.isotonic import IsotonicRegression
from sqlalchemy.orm import Session, sessionmaker

from src.core.db import get_engine
from src.core.redis_client import get_redis as _get_redis_client
from src.models.artifacts import LoadedModel

_log = logging.getLogger(__name__)

_session_factory: sessionmaker | None = None


def _get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped SQLAlchemy session; close on exit."""
    session = _get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_redis() -> Redis:
    """Returns the process-wide Redis client. Graceful-degrade if down
    is handled by the cache decorator, not here."""
    return _get_redis_client()


def get_model(request: Request) -> LoadedModel:
    """Return the model loaded at app startup. 503 if unavailable."""
    m = getattr(request.app.state, "loaded_model", None)
    if m is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="model not loaded",
        )
    return m


def get_calibrator(request: Request) -> IsotonicRegression | None:
    """Calibrator is optional — routes that need it should handle None."""
    return getattr(request.app.state, "calibrator", None)


def get_explainer(request: Request):
    """Lazy SHAP explainer. Cached on app.state after first use."""
    if getattr(request.app.state, "explainer", None) is None:
        import shap

        loaded = get_model(request)
        try:
            request.app.state.explainer = shap.TreeExplainer(loaded.model)
        except Exception as exc:  # noqa: BLE001
            _log.warning("SHAP explainer init failed", extra={"err": str(exc)})
            request.app.state.explainer = False  # sentinel — don't retry
    return request.app.state.explainer or None
