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
