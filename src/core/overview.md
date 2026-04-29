# core

## Purpose
Process-wide infrastructure primitives: settings loading, SQLAlchemy engine + session, Redis client, and structured logging. Every other `src/` module depends on this one; nothing here depends on anything else in `src/`.

## Entry points
- `config.py` — `Settings` (Pydantic v2) + `get_settings()` cached factory. Reads `.env`.
- `db.py` — `get_engine()` returns a cached SQLAlchemy `Engine`; `get_session()` is a context manager that commits on success and rolls back on exception.
- `redis_client.py` — `get_redis()` returns a cached `redis.Redis` client (`decode_responses=True`).
- `logging_config.py` — `configure_logging(level=None)` installs a JSON-line stdout handler on the root logger; `JsonFormatter` is the formatter class, callable directly for tests.
- `time.py` — `current_mlb_date(now=None)` returns the active MLB slate date in America/New_York; naive injected datetimes are treated as ET for deterministic tests.

## Public interface
```python
from src.core.config import Settings, get_settings
from src.core.db import get_engine, get_session
from src.core.redis_client import get_redis
from src.core.logging_config import configure_logging, JsonFormatter
from src.core.time import current_mlb_date
```

## Internal dependencies
None within `src/`. External: `pydantic`, `pydantic-settings`, `sqlalchemy`, `psycopg`, `redis`.

## Gotchas
- `get_settings()`, `get_engine()`, `get_redis()`, and the internal `_get_sessionmaker()` are all `@lru_cache(maxsize=1)`. Tests that monkeypatch env vars must clear the relevant cache (`get_settings.cache_clear()`).
- `configure_logging()` is idempotent: calling it twice does not double-attach handlers. The `level` arg is honored only on the first call.
- `Settings.model_config` uses `extra="ignore"`, so unknown env vars in `.env` are silently dropped — intentional, but be aware when debugging missing config.
- The DB URL scheme is `postgresql+psycopg://` (psycopg3), NOT `postgresql://` (psycopg2).
- Use `current_mlb_date()` for slate-facing pipeline/API defaults. Plain `date.today()` or UTC `datetime.now(UTC).date()` can flip to the next day before late West Coast games finish.
