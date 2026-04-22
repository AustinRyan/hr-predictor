# Phase 0 Notes

## Implementation discoveries

- **uv resolved Python 3.12.12** automatically (no system Python 3.12 was installed). Pin range `>=3.12,<3.13` in `pyproject.toml` keeps us off 3.13/3.14 until the heavy deps (xgboost, lightgbm, shap) catch up.
- **`postgresql+psycopg://` URL scheme is required** — the bare `postgresql://` form defaults SQLAlchemy to psycopg2, which is not in our deps.
- **Pre-commit hooks only run on staged files.** First-time verification needed `git add .` before `pre-commit run --all-files` would actually exercise hooks; committed in granular chunks afterwards so individual commits go through normal hook flow.
- **`hatchling` build backend with explicit `packages = [...]`** is needed for the src-layout because we don't have a top-level package matching the project name. Listed each `src/<module>` explicitly.
- **`asyncio_mode = "auto"`** in `pytest.ini_options` is set in advance for Phase 6 (FastAPI async tests). No async tests exist yet in Phase 0.
- **`@lru_cache(maxsize=1)`** is the chosen process-wide singleton pattern for `get_settings`, `get_engine`, `get_redis`, and the internal sessionmaker. Tests that override env need to call `.cache_clear()` on the relevant accessor.
- **`configure_logging` is idempotent** — second calls are no-ops to avoid double handlers in long-running processes (and tests).
- **Coverage gate ≥80%** on `src/core/` — Phase 0 ships at 100%; achieved by adding `tests/test_core.py` covering `get_session()` happy/error paths and the `JsonFormatter` + `configure_logging` surface.

## Things to watch in later phases

- macOS may need `psql` / `redis-cli` installed locally for the manual acceptance commands. The container-exec equivalents (`docker exec hrp-postgres psql ...`) work without host clients.
- Pre-commit hooks pin tool versions independently of `pyproject.toml`. If a CI tool version drifts from the dev one, lint output may differ — keep them aligned.
