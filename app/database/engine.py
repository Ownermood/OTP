"""Engine and session factory."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import ROOT_DIR
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_engine(database_url: str, echo: bool = False) -> AsyncEngine:
    """Build the async engine, creating the SQLite directory if needed."""
    if database_url.startswith("sqlite"):
        _ensure_sqlite_dir(database_url)

    engine = create_async_engine(database_url, echo=echo, pool_pre_ping=True)

    if database_url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            # WAL keeps the poller's reads from blocking a purchase's write, and
            # foreign_keys must be on per-connection for ON DELETE CASCADE to work.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def check_connection(engine: AsyncEngine) -> bool:
    """Ping the database. Used by startup checks and the admin health screen."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("database.unreachable", error=str(exc))
        return False


def _ensure_sqlite_dir(database_url: str) -> None:
    path = database_url.split("///", 1)[-1]
    if path and path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)


async def pending_migrations(engine: AsyncEngine) -> str | None:
    """Describe the schema gap, or ``None`` when the database is up to date.

    Startup used to check only that the database answered, so a database that
    had never been migrated passed the check and then failed on every worker
    tick with ``no such table``. Connecting is not the same as being usable.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(ROOT_DIR / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()

    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            current = result.scalar()
    except Exception:
        # No alembic_version table at all: the schema was never created.
        current = None

    if current == head:
        return None
    if current is None:
        return "the schema has never been created"
    return f"the schema is at {current}, but {head} is expected"
