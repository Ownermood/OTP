"""Backups.

The database holds every balance, so these tests are about the snapshot being
consistent, complete, and not left lying around afterwards.
"""

import sqlite3

import pytest

from app.services.backup import BackupService


@pytest.fixture
def sqlite_engine(tmp_path):
    """A real file-backed database, since the point is copying a real file."""
    from sqlalchemy.ext.asyncio import create_async_engine

    path = tmp_path / "bot.db"
    return create_async_engine(f"sqlite+aiosqlite:///{path}"), f"sqlite+aiosqlite:///{path}"


@pytest.fixture
async def populated(sqlite_engine):
    """A database with a user carrying a balance, as production would have."""
    from app.database.base import Base
    from app.database.models import User

    engine, url = sqlite_engine
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(User(id=4242, username="saver", balance=123_456))
        await session.commit()

    yield engine, url
    await engine.dispose()


async def test_a_snapshot_contains_the_data(populated):
    engine, url = populated
    service = BackupService(engine, url)

    async with service.snapshot() as (path, size):
        assert size > 0
        # Open the copy as a plain database and read the balance back out.
        copy = sqlite3.connect(path)
        row = copy.execute("select balance from users where id = 4242").fetchone()
        copy.close()

    assert row == (123_456,)


async def test_the_snapshot_is_deleted_afterwards(populated):
    """A file with every balance must not be left on disk."""
    engine, url = populated
    service = BackupService(engine, url)

    async with service.snapshot() as (path, _size):
        assert path.exists()
    assert not path.exists()
    assert not path.parent.exists()


async def test_the_snapshot_survives_writes_during_the_copy(populated):
    """VACUUM INTO is used precisely so the bot need not stop to be backed up."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.database.models import User

    engine, url = populated
    service = BackupService(engine, url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with service.snapshot() as (path, _size):
        async with factory() as session:
            session.add(User(id=5252, username="later", balance=1))
            await session.commit()

        copy = sqlite3.connect(path)
        count = copy.execute("select count(*) from users").fetchone()[0]
        copy.close()

    # The copy is a point-in-time snapshot; it is intact either way.
    assert count in (1, 2)


async def test_every_table_is_in_the_copy(populated):
    engine, url = populated

    async with BackupService(engine, url).snapshot() as (path, _size):
        copy = sqlite3.connect(path)
        tables = {r[0] for r in copy.execute("select name from sqlite_master where type='table'")}
        copy.close()

    for expected in ("users", "orders", "transactions", "payments", "promo_codes"):
        assert expected in tables


def test_postgres_is_declined_rather_than_faked():
    service = BackupService(None, "postgresql+asyncpg://user:pw@db/bot")
    assert service.supported is False


async def test_an_unsupported_database_raises_rather_than_writing_nothing():
    from app.services.backup import BackupError

    service = BackupService(None, "postgresql+asyncpg://user:pw@db/bot")
    with pytest.raises(BackupError):
        async with service.snapshot():
            pass


def test_filenames_sort_chronologically():
    from datetime import datetime

    earlier = BackupService.filename(datetime(2026, 1, 2, 3, 4))
    later = BackupService.filename(datetime(2026, 1, 2, 5, 6))

    assert earlier < later
    assert earlier == "bot-backup-2026-01-02_03-04.sqlite"


def test_the_telegram_size_limit_is_respected():
    assert BackupService.too_large(49 * 1024 * 1024) is False
    assert BackupService.too_large(51 * 1024 * 1024) is True


def test_a_hostile_path_is_refused():
    """The path goes into SQL unparameterised, so it is checked."""
    from pathlib import Path

    from app.services.backup import BackupError, _sql_literal

    assert _sql_literal(Path("/tmp/ok/backup.sqlite"))
    with pytest.raises(BackupError):
        _sql_literal(Path("/tmp/x'; drop table users; --"))
