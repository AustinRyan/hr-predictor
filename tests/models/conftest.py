"""Model-suite fixtures.

Overrides the session-wide ``db_engine`` with a dedicated connection to
the primary dev DB (``hrp``). The shared ``db_engine`` in
``tests/conftest.py`` resolves via ``get_engine()`` which reads
``DATABASE_URL`` at creation time. When the ingestion suite's
``test_engine`` fixture has already flipped that env var to the
``hrp_test`` DB (and cleared the lru_cache), any later ``db_engine``
request would silently return an engine pointed at ``hrp_test`` — which
is a freshly migrated, empty schema with zero ``matchup_features``
rows. Our integration tests need the real 668k-row historical backfill.

Scoped to ``tests/models/`` only so we don't affect any other suite.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

_PRIMARY_URL = "postgresql+psycopg://hrp:hrp@localhost:5432/hrp"


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """Engine pinned to the primary dev DB, independent of env overrides."""
    engine = create_engine(_PRIMARY_URL, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.fail(
            "Could not reach the primary dev Postgres (hrp). "
            "These tests require docker-compose services. "
            f"Underlying error: {exc}"
        )
    try:
        yield engine
    finally:
        engine.dispose()
