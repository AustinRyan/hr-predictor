from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return a process-wide cached SQLAlchemy Engine."""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache(maxsize=1)
def _get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a SQLAlchemy session, committing on success and rolling back on error."""
    session = _get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
