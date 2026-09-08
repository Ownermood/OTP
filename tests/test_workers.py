"""Background workers, driven directly."""

from datetime import datetime, timedelta

import pytest

from app.core.constants import OrderKind, OrderStatus, TransactionType
from app.database.repositories import OrderRepository
from app.services.workers import ORPHAN_GRACE_SECONDS, SmsWorker
from tests.fakes import FakeSmsProvider


class RecordingNotifier:
    """Stands in for the notification service and remembers what it sent."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def notify_user(self, user_id: int, text: str, **_kwargs) -> bool:
        self.sent.append((user_id, text))
        return True

    async def notify_admins(self, text: str) -> None:
        self.sent.append((0, text))


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def sms_worker(session_factory, notifier, settings) -> SmsWorker:
    provider = FakeSmsProvider()
    worker = SmsWorker(
        session_factory, provider, notifier, settings, lambda key, **kw: key
    )
    worker.provider = provider
    return worker


async def _charged_but_unsent(session_factory, user_id: int, age_seconds: int):
    """An order that was paid for but never reached the provider."""
    from app.services.wallet import WalletService

    async with session_factory() as session:
        from app.database.models import User

        if await session.get(User, user_id) is None:
            session.add(User(id=user_id, username="t", balance=10_000))
            await session.commit()

        order = await OrderRepository(session).create(
            user_id=user_id,
            kind=OrderKind.ACTIVATION,
            status=OrderStatus.PENDING,
            provider="fake_sms",
            service_code="wa",
            service_name="WhatsApp",
            country_id=22,
            country_name="India",
            price=1_100,
        )
        await WalletService(session).debit(
            user_id, 1_100, TransactionType.PURCHASE, f"purchase:order:{order.id}"
        )
        order.created_at = datetime.utcnow() - timedelta(seconds=age_seconds)
        await session.commit()
        return order.id


async def test_the_worker_refunds_an_order_that_never_reached_the_provider(
    session_factory, sms_worker, notifier
):
    """Regression: this order was charged for and no path would ever resolve it."""
    from app.services.wallet import WalletService

    order_id = await _charged_but_unsent(
        session_factory, 1001, age_seconds=ORPHAN_GRACE_SECONDS + 60
    )

    await sms_worker.tick()

    async with session_factory() as session:
        order = await OrderRepository(session).get(order_id)
        assert order.status == OrderStatus.FAILED
        assert await WalletService(session).get_balance(1001) == 10_000

    assert notifier.sent == [(1001, "sms.failed")]


async def test_an_in_flight_purchase_is_not_swept(session_factory, sms_worker, notifier):
    """A purchase mid-call has no provider id yet and must be left alone."""
    from app.services.wallet import WalletService

    order_id = await _charged_but_unsent(session_factory, 1002, age_seconds=5)

    await sms_worker.tick()

    async with session_factory() as session:
        order = await OrderRepository(session).get(order_id)
        assert order.status == OrderStatus.PENDING
        assert await WalletService(session).get_balance(1002) == 8_900

    assert notifier.sent == []


async def test_the_worker_delivers_an_sms_and_closes_the_order(
    session_factory, sms_worker, notifier
):
    from app.providers.base import ActivationStatus
    from app.services.wallet import WalletService

    async with session_factory() as session:
        from app.database.models import User

        session.add(User(id=1003, username="t", balance=10_000))
        await session.commit()
        order = await OrderRepository(session).create(
            user_id=1003,
            kind=OrderKind.ACTIVATION,
            status=OrderStatus.PROCESSING,
            provider="fake_sms",
            provider_order_id="prov-9",
            service_code="wa",
            service_name="WhatsApp",
            country_id=22,
            country_name="India",
            price=1_100,
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        )
        await WalletService(session).debit(
            1003, 1_100, TransactionType.PURCHASE, f"purchase:order:{order.id}"
        )
        await session.commit()
        order_id = order.id

    sms_worker.provider.status = ActivationStatus(state="received", code="654321")
    await sms_worker.tick()

    async with session_factory() as session:
        order = await OrderRepository(session).get(order_id)
        assert order.status == OrderStatus.SUCCESS
        assert order.sms_code == "654321"
        # A delivered code is not refunded.
        assert await WalletService(session).get_balance(1003) == 8_900

    assert notifier.sent == [(1003, "sms.received")]


async def test_an_expired_activation_is_refunded(session_factory, sms_worker, notifier):
    from app.services.wallet import WalletService

    async with session_factory() as session:
        from app.database.models import User

        session.add(User(id=1004, username="t", balance=10_000))
        await session.commit()
        order = await OrderRepository(session).create(
            user_id=1004,
            kind=OrderKind.ACTIVATION,
            status=OrderStatus.PROCESSING,
            provider="fake_sms",
            provider_order_id="prov-8",
            service_code="wa",
            service_name="WhatsApp",
            country_id=22,
            country_name="India",
            price=1_100,
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )
        await WalletService(session).debit(
            1004, 1_100, TransactionType.PURCHASE, f"purchase:order:{order.id}"
        )
        await session.commit()
        order_id = order.id

    await sms_worker.tick()

    async with session_factory() as session:
        order = await OrderRepository(session).get(order_id)
        assert order.status == OrderStatus.EXPIRED
        assert await WalletService(session).get_balance(1004) == 10_000

    assert notifier.sent == [(1004, "sms.expired")]


async def test_an_idle_worker_backs_off(session_factory, sms_worker):
    """Nothing in flight must not mean hammering the provider."""
    from app.services.workers import IDLE_INTERVAL

    assert await sms_worker.tick() == IDLE_INTERVAL


async def test_a_failing_poll_does_not_kill_the_loop(session_factory, sms_worker, notifier):
    """One bad order must not take the worker down."""

    async def explode(*_args, **_kwargs):
        raise RuntimeError("provider exploded")

    await _charged_but_unsent(session_factory, 1005, age_seconds=5)
    sms_worker.provider.get_activation_status = explode

    # tick() itself must not raise; BaseWorker's loop logs and carries on.
    await sms_worker.tick()
