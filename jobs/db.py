"""Database connection for ArchonAI's background jobs.

Everything here is lazy: no connection is opened at import time, and the
tables are only created the first time a job is actually stored or read.
That keeps the API's /health and synchronous endpoints working on a machine
where MySQL isn't running -- only the job endpoints need a database.

The engine is cached per DATABASE_URL, so tests can point the job system at
SQLite by changing the environment and calling reset_engine().
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from jobs.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for every job-system table."""


_engine: Engine | None = None
_engine_url: str | None = None
_session_factory: sessionmaker[Session] | None = None
_tables_created = False


def _build_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        # In-memory SQLite (used by tests) is per-connection, so every thread
        # must share the one connection or each would see an empty database.
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    # pool_pre_ping: transparently replace connections MySQL has closed (its
    # default wait_timeout drops idle connections after 8 hours), instead of
    # failing the next request with "MySQL server has gone away".
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


def get_engine() -> Engine:
    """Return the engine for the current DATABASE_URL, creating it on first use."""
    global _engine, _engine_url, _session_factory, _tables_created
    url = get_settings().database_url
    if _engine is None or url != _engine_url:
        if _engine is not None:
            _engine.dispose()
        _engine = _build_engine(url)
        _engine_url = url
        # expire_on_commit=False: job objects stay readable after the session
        # that loaded them commits, so callers can return them directly.
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
        _tables_created = False
    return _engine


def init_db() -> None:
    """Create the job tables if they don't exist yet (idempotent, runs once per engine)."""
    global _tables_created
    engine = get_engine()
    if _tables_created:
        return
    # Imported here so every model is registered on Base before create_all,
    # without making this module depend on the models at import time.
    import jobs.models  # noqa: F401

    Base.metadata.create_all(engine)
    _tables_created = True


@contextmanager
def session_scope() -> Iterator[Session]:
    """A transactional session: commits on success, rolls back on any error."""
    init_db()
    assert _session_factory is not None  # set by get_engine() via init_db()
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Dispose the cached engine (used by tests to switch databases cleanly)."""
    global _engine, _engine_url, _session_factory, _tables_created
    if _engine is not None:
        _engine.dispose()
    _engine = _engine_url = _session_factory = None
    _tables_created = False
