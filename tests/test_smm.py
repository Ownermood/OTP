"""SMM ordering follows the same money rules as the SMS flow."""

import pytest

from app.core.constants import OrderKind, OrderStatus
from app.core.exceptions import ProviderError, ValidationError
from app.services.smm import SmmService
from tests.fakes import FakeSmmProvider


@pytest.fixture
def provider() -> FakeSmmProvider:
    return FakeSmmProvider()


@pytest.fixture
def smm(session, provider, zero_fee_pricing, wallet, settings) -> SmmService:
    settings.smm_markup_percent = 0
    return SmmService(session, provider, zero_fee_pricing, wallet, settings)


async def test_categories_are_derived_from_the_catalogue(smm):
    categories = await smm.categories()
    assert [c.value for c, _ in categories] == ["instagram"]


async def test_quote_prorates_the_panel_rate(smm):
    service = await smm.find_service("101")
    # 100.00 per 1000 followers, ordering 500 => 50.00
    assert smm.quote(service, 500).total == 5_000


async def test_quantity_bounds_are_enforced(smm):
    service = await smm.find_service("101")
    with pytest.raises(ValidationError):
        smm.quote(service, 1)
    with pytest.raises(ValidationError):
        smm.quote(service, 999_999)


async def test_order_charges_and_records_the_provider_id(smm, user, wallet, provider):
    purchase = await smm.create_order(
        user_id=user.id,
        service_id="101",
        link="https://instagram.com/example",
        quantity=100,
        quoted_price=1_000,
    )

    assert purchase.order.kind == OrderKind.SMM
    assert purchase.order.provider_order_id == "smm-1"
    assert purchase.order.status == OrderStatus.PROCESSING
    assert (await wallet.get_balance(user.id)) == 9_000


async def test_panel_rejection_refunds_the_user(smm, user, wallet, provider):
    provider.fail_next = True

    with pytest.raises(ProviderError):
        await smm.create_order(user.id, "101", "https://x.test/a", 100, 1_000)

    assert (await wallet.get_balance(user.id)) == 10_000


async def test_a_withdrawn_service_cannot_be_ordered(smm, user):
    with pytest.raises(ValidationError):
        await smm.create_order(user.id, "does-not-exist", "https://x.test/a", 100, 1_000)


async def test_cancelled_panel_order_is_refunded_once(smm, user, wallet, provider):
    from app.providers.base import SmmOrderStatus

    purchase = await smm.create_order(user.id, "101", "https://x.test/a", 100, 1_000)
    provider.status = SmmOrderStatus(state="cancelled")

    await smm.refresh_status(purchase.order)
    await smm.refresh_status(purchase.order)  # a second poll must not pay twice

    assert purchase.order.status == OrderStatus.CANCELLED
    assert (await wallet.get_balance(user.id)) == 10_000


async def test_completed_order_is_not_refunded(smm, user, wallet, provider):
    from app.providers.base import SmmOrderStatus

    purchase = await smm.create_order(user.id, "101", "https://x.test/a", 100, 1_000)
    provider.status = SmmOrderStatus(state="success", start_count=10, remains=0)

    await smm.refresh_status(purchase.order)

    assert purchase.order.status == OrderStatus.SUCCESS
    assert (await wallet.get_balance(user.id)) == 9_000


async def test_user_cannot_read_another_users_smm_order(session, smm, user):
    from app.core.exceptions import OrderNotFoundError
    from app.database.models import User

    session.add(User(id=9009, username="other", balance=0))
    await session.commit()

    purchase = await smm.create_order(user.id, "101", "https://x.test/a", 100, 1_000)

    with pytest.raises(OrderNotFoundError):
        await smm.get_owned(purchase.order.id, 9009)


async def test_disabled_module_reports_itself(session, zero_fee_pricing, wallet, settings):
    disabled = SmmService(session, None, zero_fee_pricing, wallet, settings)
    assert disabled.enabled is False
    assert await disabled.services() == []
