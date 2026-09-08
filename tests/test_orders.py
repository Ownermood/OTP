"""Purchase-path guarantees: no double charge, no charge without a number."""

import pytest

from app.core.constants import OrderKind, OrderStatus
from app.core.exceptions import (
    DuplicateOperationError,
    InsufficientBalanceError,
    NoNumbersAvailableError,
    StalePriceError,
)
from app.database.repositories import OrderRepository, TransactionRepository
from app.services.orders import OrderService
from tests.fakes import FakeSmsProvider


@pytest.fixture
def provider() -> FakeSmsProvider:
    return FakeSmsProvider(cost=1_000)


@pytest.fixture
def orders(session, provider, pricing, wallet, settings) -> OrderService:
    return OrderService(session, provider, pricing, wallet, settings)


async def _buy(orders: OrderService, user_id: int, quoted: int = 1_100):
    return await orders.purchase_activation(
        user_id=user_id,
        service_code="wa",
        service_name="WhatsApp",
        country_id=22,
        country_name="India",
        quoted_price=quoted,
    )


async def test_purchase_charges_the_live_price_not_the_quote(orders, user, wallet):
    """The quote is a display value; the charge comes from the live price."""
    result = await _buy(orders, user.id, quoted=1_100)

    # 1000 provider cost + 10% configured fee = 1100.
    assert result.order.price == 1_100
    assert result.balance_after == 10_000 - 1_100
    assert (await wallet.get_balance(user.id)) == 8_900


async def test_purchase_records_the_provider_order_id(orders, user, provider):
    result = await _buy(orders, user.id)
    assert result.order.provider_order_id == "prov-1"
    assert result.order.phone.startswith("+91")
    assert result.order.status == OrderStatus.PROCESSING


async def test_stale_quote_is_rejected(orders, user, provider):
    """A quote from before a price rise must not buy at the old price."""
    provider.cost = 5_000  # price tripled since the user saw the quote

    with pytest.raises(StalePriceError):
        await _buy(orders, user.id, quoted=1_100)

    assert provider.created == 0


async def test_small_upward_drift_is_absorbed(orders, user, provider):
    provider.cost = 1_050  # 5.50 final vs 11.00 quoted — within tolerance
    result = await _buy(orders, user.id, quoted=1_100)
    assert result.order.price == 1_155


async def test_double_click_cannot_buy_twice(orders, user, provider):
    """A second identical in-flight purchase is refused."""
    await _buy(orders, user.id)

    with pytest.raises(DuplicateOperationError):
        await _buy(orders, user.id)

    assert provider.created == 1


async def test_insufficient_balance_never_reaches_the_provider(orders, session, provider):
    from app.database.models import User

    session.add(User(id=3003, username="broke", balance=100))
    await session.commit()

    with pytest.raises(InsufficientBalanceError):
        await _buy(orders, 3003)

    assert provider.created == 0


async def test_provider_failure_refunds_the_user(orders, session, user, wallet, provider):
    """The user is never charged for a number they did not get."""
    provider.fail_next = True

    with pytest.raises(NoNumbersAvailableError):
        await _buy(orders, user.id)

    assert (await wallet.get_balance(user.id)) == 10_000

    order = (await OrderRepository(session).list_for_user(user.id))[0]
    assert order.status == OrderStatus.FAILED
    assert order.refunded_at is not None

    # Both legs are on the record: the debit and the refund.
    types = [t.type for t in await TransactionRepository(session).list_for_user(user.id)]
    assert types == ["refund", "purchase"]


async def test_cancel_refunds_once(orders, session, user, wallet, provider):
    result = await _buy(orders, user.id)
    assert (await wallet.get_balance(user.id)) == 8_900

    await orders.cancel(result.order.id, user.id)
    assert (await wallet.get_balance(user.id)) == 10_000
    assert provider.cancelled == ["prov-1"]

    # Cancelling again must not pay out a second time.
    with pytest.raises(DuplicateOperationError):
        await orders.cancel(result.order.id, user.id)
    assert (await wallet.get_balance(user.id)) == 10_000


async def test_expiry_refunds_once(orders, session, user, wallet):
    result = await _buy(orders, user.id)

    await orders.expire(result.order)
    await orders.expire(result.order)

    assert (await wallet.get_balance(user.id)) == 10_000
    assert result.order.status == OrderStatus.EXPIRED


async def test_sms_received_completes_without_refund(orders, session, user, wallet, provider):
    result = await _buy(orders, user.id)

    await orders.mark_sms_received(result.order, "123456", "Your code is 123456")

    assert result.order.status == OrderStatus.SUCCESS
    assert result.order.sms_code == "123456"
    assert result.order.refunded_at is None
    assert (await wallet.get_balance(user.id)) == 8_900
    assert provider.finished == ["prov-1"]


async def test_user_cannot_read_another_users_order(orders, session, user):
    """Order ids come from callback data; ownership is checked server-side."""
    from app.core.exceptions import OrderNotFoundError
    from app.database.models import User

    session.add(User(id=4004, username="other", balance=10_000))
    await session.commit()

    result = await _buy(orders, user.id)

    with pytest.raises(OrderNotFoundError):
        await orders.get_owned(result.order.id, 4004)

    with pytest.raises(OrderNotFoundError):
        await orders.cancel(result.order.id, 4004)


async def test_rental_creates_a_rental_order(orders, user, settings):
    result = await orders.purchase_rental(
        user_id=user.id,
        service_code="full",
        service_name="Any service",
        country_id=22,
        country_name="India",
        hours=24,
        quoted_price=2_000,
    )

    assert result.order.kind == OrderKind.RENTAL
    assert result.order.rental_hours == 24
    assert result.order.provider_order_id == "rent-1"


async def test_rental_duration_is_validated(orders, user, settings):
    from app.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        await orders.purchase_rental(
            user_id=user.id,
            service_code="full",
            service_name="Any",
            country_id=22,
            country_name="India",
            hours=settings.max_rental_hours + 1,
            quoted_price=1_000,
        )
