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
    RATE_LIMIT_PER_SECOND="1000",
    UPI_ID="shop@okaxis",
    UPI_PAYEE_NAME="Test Shop",
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


@pytest_asyncio.fixture
async def harness(session_factory, settings, monkeypatch):
    """A running bot, wired exactly as production wires it, with fake providers."""
    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.fsm.storage.memory import MemoryStorage

    from app.bot.handlers import build_router
    from app.bot.setup import _register_drain, _register_middlewares
    from app.bot.texts import Texts
    from app.core.config import ROOT_DIR
    from app.services.catalog import CatalogService
    from app.services.notifications import NotificationService
    from app.utils.tokens import TokenStore
    from tests.fakes import FakePaymentProvider, FakeSmmProvider, FakeSmsProvider
    from tests.harness import BotHarness, MockedSession

    mocked = MockedSession()
    bot = Bot(
        token="424242:TEST-TOKEN-FOR-HARNESS-ONLY",
        session=mocked,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())

    sms_provider = FakeSmsProvider(cost=1_000)
    payment_provider = FakePaymentProvider()
    smm_provider = FakeSmmProvider()
    pricing = PricingService(settings)

    dispatcher.workflow_data.update(
        settings=settings,
        texts=Texts(ROOT_DIR / "locales", settings.locale),
        pricing=pricing,
        catalog=CatalogService(sms_provider, pricing, settings),
        engine=None,
        session_factory=session_factory,
        sms_provider=sms_provider,
        payment_providers={payment_provider.name: payment_provider},
        smm_provider=smm_provider,
        smm_cache=None,
        notifications=NotificationService(bot, session_factory, settings.admin_ids),
        tokens=TokenStore(),
    )
    # Handler routers are module-level singletons: built once in production,
    # but every test builds its own dispatcher. Detach them first so they can
    # be re-attached to this one.
    from app.bot.handlers import (
        admin,
        buy,
        manual_payments,
        orders,
        profile,
        smm,
        start,
        wallet,
    )

    for module in (
        admin, start, buy, orders, wallet, manual_payments, smm, profile
    ):
        module.router._parent_router = None

    # The same registration production uses, so the harness cannot drift from
    # what actually runs.
    _register_middlewares(dispatcher, settings, session_factory)
    _register_drain(dispatcher, settings)
    dispatcher.include_router(build_router())

    driver = BotHarness(bot, dispatcher, mocked, user_id=555001)
    # Exposed so tests can steer the fakes mid-flow.
    driver.sms = sms_provider
    driver.payments = payment_provider
    driver.smm = smm_provider
    yield driver

    await bot.session.close()
