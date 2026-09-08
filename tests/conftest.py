"""Test fixtures.

Every test runs against a real in-memory SQLite database with the real
repositories and services -- the money guarantees are only worth testing
against actual constraint enforcement.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Settings are constructed from the environment, so give the tests a valid one
# before app.core.config is imported anywhere.
os.environ.update(
    BOT_TOKEN="123456789:TEST-TOKEN-FOR-UNIT-TESTS-ONLY",
    ADMIN_IDS="1",
    SMS_ACTIVATE_API_TOKEN="test-key",
    TELEGRAM_STARS_ENABLED="true",
    CRYPTOBOT_ENABLED="false",
    DATABASE_URL="sqlite+aiosqlite:///:memory:",
    SERVICE_FEE_PERCENT="10",
    SMM_ENABLED="false",
)

from app.core.config import Settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.models import User  # noqa: E402
from app.services.pricing import PricingService  # noqa: E402
from app.services.wallet import WalletService  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


@pytest_asyncio.fixture
async def session_factory():
    """A fresh in-memory database per test, with the real schema."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def session(session_factory):
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def user(session) -> User:
    """A user with a 100.00 balance (10 000 minor units)."""
    user = User(id=1001, username="tester", full_name="Test User", balance=10_000)
    session.add(user)
    await session.commit()
    return user


@pytest.fixture
def wallet(session) -> WalletService:
    return WalletService(session)


@pytest.fixture
def pricing(settings) -> PricingService:
    return PricingService(settings)


@pytest.fixture
def zero_fee_pricing(settings) -> PricingService:
    settings.service_fee_percent = Decimal("0")
    settings.service_fee_fixed = Decimal("0")
    return PricingService(settings)
