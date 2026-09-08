"""Database backups.

The database holds every user's balance. Losing it means being unable to honour
a single deposit, so a backup is not housekeeping -- it is the difference
between a bad day and having to tell users their money is gone.

Snapshots use SQLite's ``VACUUM INTO``, which writes a consistent copy while
the bot keeps running. Copying the file directly would not: with WAL enabled
the copy can land mid-transaction, and the recent writes live in a separate
``-wal`` file that a naive copy leaves behind.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.exceptions import BotError
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Telegram refuses documents above 50 MB from a bot.
TELEGRAM_FILE_LIMIT = 50 * 1024 * 1024


class BackupError(BotError):
    message_key = "errors.generic"


class BackupService:
    """Takes consistent snapshots of the database."""

    def __init__(self, engine: AsyncEngine, database_url: str) -> None:
        self._engine = engine
        self._url = database_url

    @property
    def supported(self) -> bool:
        """Only SQLite is snapshotted here.

        A Postgres deployment has ``pg_dump`` and a backup story of its own;
        pretending to cover it from inside the bot would be worse than saying
        plainly that it does not.
        """
        return self._url.startswith("sqlite")

    @asynccontextmanager
    async def snapshot(self):
        """Yield a path to a consistent copy, and clean it up afterwards.

        The copy lives in a temporary directory that is removed on exit, so a
        file containing every balance is never left lying on disk.
        """
        if not self.supported:
            raise BackupError("backups are only built in for SQLite")

        with TemporaryDirectory(prefix="bot-backup-") as directory:
            target = Path(directory) / self.filename()
            async with self._engine.connect() as connection:
                # The path is interpolated, so refuse anything but our own.
                await connection.execute(text(f"VACUUM INTO '{_sql_literal(target)}'"))

            size = target.stat().st_size
            logger.info("backup.created", bytes=size, name=target.name)
            yield target, size

    @staticmethod
    def filename(moment: datetime | None = None) -> str:
        """A name that sorts chronologically and is safe on every filesystem."""
        stamp = (moment or datetime.utcnow()).strftime("%Y-%m-%d_%H-%M")
        return f"bot-backup-{stamp}.sqlite"

    @staticmethod
    def too_large(size: int) -> bool:
        return size > TELEGRAM_FILE_LIMIT


def _sql_literal(path: Path) -> str:
    """Render a path for a SQL string literal.

    ``VACUUM INTO`` takes no bind parameters, so the path is interpolated. It
    is one we generate inside a temporary directory, never user input, and this
    rejects anything that could close the quote regardless.
    """
    rendered = str(path)
    if "'" in rendered or not re.fullmatch(r"[\w\-./]+", rendered):
        raise BackupError(f"refusing to write a backup to {rendered!r}")
    return rendered
