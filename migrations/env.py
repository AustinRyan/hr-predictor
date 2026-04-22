"""Alembic environment wired to `src.core`.

Reads the database URL from the project `Settings` (which loads from `.env`)
and uses `Base.metadata` from `src.core.models` as the autogenerate target.
Autogenerate is a convenience; the partitioned `statcast_pitches` table
requires explicit DDL in the migration body.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from src.core.config import get_settings
from src.core.db import get_engine
from src.core.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject DATABASE_URL at runtime so alembic.ini stays secret-free.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = get_engine()
    with engine.connect() as connection:
        _do_run_migrations(connection)

    # NullPool fallback if anyone overrides the URL via config; keeps parity
    # with stock alembic init behavior for out-of-band invocations.
    if engine.pool is None:
        alt = pool.NullPool()
        with alt.connect() as connection:
            _do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
