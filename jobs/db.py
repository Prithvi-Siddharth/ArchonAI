"""Database connection for ArchonAI's background jobs.

Everything here is lazy: no connection is opened at import time, and the
tables are only created the first time a job is actually stored or read.
That keeps the API's /health and synchronous endpoints working on a machine
where MySQL isn't running -- only the job endpoints need a database.

The engine is cached per DATABASE_URL, so tests can point the job system at
SQLite by changing the environment and calling reset_engine().
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError
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
    import auth.models  # noqa: F401  (the users table)
    import llm_keys.models  # noqa: F401  (the user_llm_settings table)
    import jobs.models  # noqa: F401

    # The API and the worker can both set up the schema on first use. If the other one
    # is mid-way ("table already exists", "being modified by concurrent DDL"), wait a
    # moment and run the whole setup again: every part of it is idempotent.
    for attempt in range(1, _SCHEMA_ATTEMPTS + 1):
        try:
            Base.metadata.create_all(engine)
            _add_missing_columns(engine)
            break
        except (OperationalError, ProgrammingError) as exc:
            # Anything else (e.g. the database is down) fails at once, without waiting.
            if attempt == _SCHEMA_ATTEMPTS or not _is_concurrent_schema_change(exc):
                raise
            time.sleep(0.5 * attempt)
    _tables_created = True


_SCHEMA_ATTEMPTS = 5
# MySQL: table exists, duplicate column, duplicate index, definition being changed by concurrent DDL.
_CONCURRENT_DDL_ERRORS = {1050, 1060, 1061, 1684}


def _is_concurrent_schema_change(exc: Exception) -> bool:
    """True for errors caused by another process creating the same tables/columns right now."""
    original = getattr(exc, "orig", None)
    code = original.args[0] if original is not None and original.args else None
    return code in _CONCURRENT_DDL_ERRORS or "already exists" in str(original).lower()


# Columns added to an existing table after it was first created. create_all only
# creates missing tables, never missing columns, so each one is added here in place:
# existing rows are kept, and the new column starts as NULL. There is no Alembic yet.
_ADDED_COLUMNS = [
    # (table, column, column DDL, index name)
    ("architecture_jobs", "owner_id", "VARCHAR(36) NULL", "ix_architecture_jobs_owner_id"),
]


def _add_missing_columns(engine: Engine) -> None:
    """Idempotent, and safe when the API and the worker start at the same time."""
    for table, column, ddl, index in _ADDED_COLUMNS:
        if column not in {c["name"] for c in inspect(engine).get_columns(table)}:
            try:
                with engine.begin() as connection:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            except (OperationalError, ProgrammingError):
                # Another process may have added it between our check and the ALTER.
                if column not in {c["name"] for c in inspect(engine).get_columns(table)}:
                    raise
        if index not in {i["name"] for i in inspect(engine).get_indexes(table)}:
            try:
                with engine.begin() as connection:
                    connection.execute(text(f"CREATE INDEX {index} ON {table} ({column})"))
            except (OperationalError, ProgrammingError):
                if index not in {i["name"] for i in inspect(engine).get_indexes(table)}:
                    raise


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
