"""FastAPI app factory for the HR Predictor backend."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.errors import register_error_handlers
from src.api.routers import health as health_router
from src.api.routers import picks as picks_router
from src.api.routers import player as player_router
from src.core.logging_config import configure_logging
from src.models.artifacts import load_model
from src.models.calibrate import load_calibrator

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load model + calibrator once at startup; dispose on shutdown."""
    configure_logging()
    try:
        loaded = load_model()
        app.state.loaded_model = loaded
        _log.info("model loaded", extra={"version": loaded.version})
    except FileNotFoundError:
        _log.warning("no model registry found — API will serve /health only")
        app.state.loaded_model = None

    if app.state.loaded_model is not None:
        try:
            app.state.calibrator = load_calibrator(app.state.loaded_model.version)
            _log.info("calibrator loaded")
        except FileNotFoundError:
            _log.warning(
                "no calibrator for model — predictions will be uncalibrated",
                extra={"version": app.state.loaded_model.version},
            )
            app.state.calibrator = None
    else:
        app.state.calibrator = None

    # SHAP explainer is lazy-initialized in dependencies.get_explainer.
    app.state.explainer = None

    yield

    # Cleanup (nothing to dispose for XGBoost / IsotonicRegression).


def create_app() -> FastAPI:
    app = FastAPI(
        title="HR Predictor API",
        version="0.1.0",
        description=(
            "Per-game home-run probability predictions for MLB. "
            "Serves calibrated XGBoost output from a nightly inference "
            "pipeline."
        ),
        lifespan=lifespan,
    )
    register_error_handlers(app)
    app.include_router(health_router.router)
    app.include_router(picks_router.router)
    app.include_router(player_router.router)
    return app


app = create_app()
