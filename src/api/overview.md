# api

## Purpose
FastAPI backend serving HR probability predictions from the Phase 4
model + Phase 5 calibrator. Reads from `predictions` table (populated
nightly by `src/models/inference.py`). Redis caches read endpoints.

## Modules
- `main.py` — app factory + lifespan (loads model/calibrator on startup).
- `dependencies.py` — DI for DB session, Redis, loaded model, calibrator, SHAP explainer.
- `errors.py` — consistent error body + 500 logging.
- `cache.py` — `@cached(ttl_seconds, key_prefix, ...)` decorator with graceful Redis-failure degradation.
- `routers/` — one file per endpoint group.
- `schemas/` — Pydantic response models.

Full endpoint catalog is added in Phase 6 Task 9.

## Gotchas
- Model loaded once at app startup; raised 503 if unavailable.
- Cache keys include the current production model version so new deployments auto-invalidate.
- Redis failures degrade gracefully (log warning, serve from DB).
- `/health` returns 503 (not 200) when Postgres or Redis is down.
