"""TG-Lion Telegram numbers follow the same money rules as SMS/SMM.

Refresh must never buy a second number, a timed-out number must refund
exactly once, and a duplicate purchase attempt must be refused -- these are
the properties this task's safety requirements are actually about.
"""

from datetime import datetime, timedelta

import pytest

from app.core.constants import OrderKind, OrderStatus
from app.core.exceptions import DuplicateOperationError, OrderNotFoundError, ProviderError
from app.services.telegram_numbers import TelegramNumberService
from tests.fakes import FakeTgLionProvider


@pytest.fixture
def provider() -> FakeTgLionProvider:
    return FakeTgLionProvider(cost=2_000)


@pytest.fixture
def telegram_numbers(session, provider, zero_fee_pricing, wallet, settings) -> TelegramNumberService:
    settings.tg_lion_timeout = 900
    return TelegramNumberService(session, provider, zero_fee_pricing, wallet, settings)


async def test_a_purchase_charges_and_records_the_number(telegram_numbers, user, wallet, provider):
    purchase = await telegram_numbers.purchase(user.id, "in", quoted_price=0)

    assert purchase.order.kind == OrderKind.TELEGRAM
    assert purchase.order.provider_order_id == purchase.order.phone
    assert purchase.order.phone.startswith("+1929000")
    assert purchase.order.status == OrderStatus.PROCESSING
    assert purchase.order.link == "in"  # the raw TG-Lion code, for "Buy Again"
    assert (await wallet.get_balance(user.id)) == 8_000  # 10_000 - 2_000


async def test_provider_rejection_refunds_the_user(telegram_numbers, user, wallet, provider):
    provider.fail_next = True

    with pytest.raises(ProviderError):
        await telegram_numbers.purchase(user.id, "in", quoted_price=0)

    assert (await wallet.get_balance(user.id)) == 10_000


async def test_an_unknown_country_is_refused_before_any_charge(telegram_numbers, user, wallet):
    with pytest.raises(ProviderError):
        await telegram_numbers.purchase(user.id, "zz", quoted_price=0)

    assert (await wallet.get_balance(user.id)) == 10_000


async def test_a_second_purchase_is_refused_while_one_is_open(telegram_numbers, user):
    await telegram_numbers.purchase(user.id, "in", quoted_price=0)

    with pytest.raises(DuplicateOperationError):
        await telegram_numbers.purchase(user.id, "in", quoted_price=0)


async def test_refresh_with_no_code_yet_leaves_the_order_open(telegram_numbers, user, provider):
    purchase = await telegram_numbers.purchase(user.id, "in", quoted_price=0)

    order = await telegram_numbers.refresh(purchase.order)

    assert order.status == OrderStatus.PROCESSING
    assert order.sms_code is None


async def test_refresh_never_buys_a_second_number(telegram_numbers, user, provider):
    """The single most important safety property: Refresh/Get OTP must never
    create another activation, no matter how many times it is tapped."""
    purchase = await telegram_numbers.purchase(user.id, "in", quoted_price=0)

    await telegram_numbers.refresh(purchase.order)
    await telegram_numbers.refresh(purchase.order)
    await telegram_numbers.refresh(purchase.order)

    assert provider.created == 1


async def test_a_received_code_completes_the_order(telegram_numbers, user, provider):
    from app.providers.tg_lion import TgLionCode

    purchase = await telegram_numbers.purchase(user.id, "in", quoted_price=0)
    provider.next_code = TgLionCode(code="654321")

    order = await telegram_numbers.refresh(purchase.order)

    assert order.status == OrderStatus.SUCCESS
    assert order.sms_code == "654321"
    assert order.completed_at is not None


async def test_an_already_final_order_is_not_refreshed_again(telegram_numbers, user, provider):
    from app.providers.tg_lion import TgLionCode

    purchase = await telegram_numbers.purchase(user.id, "in", quoted_price=0)
    provider.next_code = TgLionCode(code="111111")
    await telegram_numbers.refresh(purchase.order)

    provider.next_code = TgLionCode(code="222222")  # would be wrong if re-applied
    order = await telegram_numbers.refresh(purchase.order)

    assert order.sms_code == "111111"


async def test_a_timed_out_number_is_refunded_exactly_once(telegram_numbers, user, wallet, provider):
    purchase = await telegram_numbers.purchase(user.id, "in", quoted_price=0)
    purchase.order.expires_at = datetime.utcnow() - timedelta(seconds=1)

    await telegram_numbers.expire(purchase.order)
    await telegram_numbers.expire(purchase.order)  # a second sweep must not pay twice

    assert purchase.order.status == OrderStatus.EXPIRED
    assert (await wallet.get_balance(user.id)) == 10_000


async def test_refresh_past_expiry_expires_instead_of_polling(telegram_numbers, user, wallet, provider):
    purchase = await telegram_numbers.purchase(user.id, "in", quoted_price=0)
    purchase.order.expires_at = datetime.utcnow() - timedelta(seconds=1)

    order = await telegram_numbers.refresh(purchase.order)

    assert order.status == OrderStatus.EXPIRED
    assert (await wallet.get_balance(user.id)) == 10_000


async def test_cancel_refunds_once_and_a_second_cancel_is_refused(telegram_numbers, user, wallet):
    purchase = await telegram_numbers.purchase(user.id, "in", quoted_price=0)

    order = await telegram_numbers.cancel(purchase.order.id, user.id)
    assert order.status == OrderStatus.CANCELLED
    assert (await wallet.get_balance(user.id)) == 10_000

    with pytest.raises(DuplicateOperationError):
        await telegram_numbers.cancel(purchase.order.id, user.id)
    assert (await wallet.get_balance(user.id)) == 10_000  # still just the one refund


async def test_cancel_calls_no_provider_endpoint(telegram_numbers, user, provider):
    """TG-Lion has no release/cancel call in the reference implementation --
    cancelling here must be purely local bookkeeping, never an upstream call
    that could error or (worse) silently do the wrong thing."""
    purchase = await telegram_numbers.purchase(user.id, "in", quoted_price=0)
    await telegram_numbers.cancel(purchase.order.id, user.id)
    # FakeTgLionProvider exposes no cancel method at all; reaching this line
    # without an AttributeError already proves nothing was called on it.


async def test_user_cannot_read_another_users_telegram_order(session, telegram_numbers, user):
    from app.database.models import User

    session.add(User(id=9010, username="other", balance=0))
    await session.commit()

    purchase = await telegram_numbers.purchase(user.id, "in", quoted_price=0)

    with pytest.raises(OrderNotFoundError):
        await telegram_numbers.get_owned(purchase.order.id, 9010)


async def test_an_orphaned_order_is_refunded_by_the_sweep(telegram_numbers, user, wallet, session):
    """A crash between the debit and the provider call must not leave the
    user permanently charged for nothing."""
    from app.core.constants import TransactionType
    from app.database.repositories import OrderRepository

    order = await OrderRepository(session).create(
        user_id=user.id,
        kind=OrderKind.TELEGRAM,
        status=OrderStatus.PENDING,
        provider="tg_lion",
        service_code="telegram_number",
        service_name="Telegram Number",
        price=2_000,
    )
    await wallet.debit(user.id, 2_000, TransactionType.PURCHASE, f"purchase:order:{order.id}")
    await session.commit()

    await telegram_numbers.fail_orphan(order)

    assert order.status == OrderStatus.FAILED
    assert (await wallet.get_balance(user.id)) == 10_000


async def test_disabled_module_reports_itself(session, zero_fee_pricing, wallet, settings):
    disabled = TelegramNumberService(session, None, zero_fee_pricing, wallet, settings)
    assert disabled.enabled is False
    assert await disabled.countries() == []


async def test_a_stale_shown_price_never_undercuts_the_live_price(
    telegram_numbers, user, wallet, provider
):
    """The price on the confirm screen is never trusted -- the live price
    always wins, exactly like every other purchase path in the bot."""
    purchase = await telegram_numbers.purchase(user.id, "in", quoted_price=1)  # absurdly low

    assert purchase.order.price == 2_000  # the real provider cost, not 1
    assert (await wallet.get_balance(user.id)) == 8_000


async def test_purchase_prices_from_the_live_provider_call_not_the_catalogue(
    telegram_numbers, user, wallet, provider
):
    """purchase() must re-price via the provider's live get_price -- exactly
    the "authoritative price straight from the provider" rule
    OrderService.purchase_activation applies to SMS activations -- rather
    than trusting whatever cost the (TTL-cached) country listing last showed.
    """
    provider.price_override = 3_500  # what TG-Lion says right now
    # provider.cost (what get_countries()/the catalogue still shows) stays 2_000.

    purchase = await telegram_numbers.purchase(user.id, "in", quoted_price=0)

    assert purchase.order.price == 3_500
    assert purchase.order.provider_cost == 3_500
    assert (await wallet.get_balance(user.id)) == 6_500
