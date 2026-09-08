"""Deposit settlement must be exactly-once under replay."""

import pytest

from app.core.constants import PaymentStatus
from app.core.exceptions import ValidationError
from app.services.payments import PaymentService
from app.services.referrals import ReferralService
from tests.fakes import FakePaymentProvider


@pytest.fixture
def provider() -> FakePaymentProvider:
    return FakePaymentProvider()


@pytest.fixture
def payments(session, provider, wallet, settings) -> PaymentService:
    return PaymentService(
        session,
        {provider.name: provider},
        wallet,
        ReferralService(session, wallet, settings),
        settings,
    )


async def test_invoice_is_recorded_as_pending(payments, provider, user):
    payment = await payments.create_invoice(user.id, provider.name, 50_000)

    assert payment.status == PaymentStatus.PENDING
    assert payment.invoice_id == "inv-1"
    assert payment.amount == 50_000


async def test_deposit_bounds_are_enforced(payments, settings, user, provider):
    with pytest.raises(ValidationError):
        await payments.create_invoice(user.id, provider.name, 1)  # below MIN_DEPOSIT
    with pytest.raises(ValidationError):
        await payments.create_invoice(user.id, provider.name, 999_999_999)


async def test_settlement_credits_the_balance(payments, provider, user, wallet):
    payment = await payments.create_invoice(user.id, provider.name, 50_000)

    settlement = await payments.settle(provider.name, payment.invoice_id)

    assert settlement is not None
    assert settlement.credited is True
    assert settlement.payment.status == PaymentStatus.PAID
    assert (await wallet.get_balance(user.id)) == 60_000


async def test_replayed_callback_does_not_credit_twice(payments, provider, user, wallet):
    """The webhook-replay guarantee, end to end."""
    payment = await payments.create_invoice(user.id, provider.name, 50_000)

    first = await payments.settle(provider.name, payment.invoice_id)
    second = await payments.settle(provider.name, payment.invoice_id)
    third = await payments.settle(provider.name, payment.invoice_id)

    assert first.credited is True
    assert second.credited is False
    assert third.credited is False
    assert (await wallet.get_balance(user.id)) == 60_000


async def test_unknown_invoice_is_ignored(payments, provider):
    assert await payments.settle(provider.name, "does-not-exist") is None


async def test_referral_commission_is_paid_once_per_deposit(
    session, payments, provider, user, wallet, settings
):
    from app.database.models import User

    inviter = User(id=5005, username="inviter", balance=0)
    session.add(inviter)
    await session.commit()

    referrals = ReferralService(session, wallet, settings)
    await referrals.link(inviter.id, user.id)
    await session.commit()

    payment = await payments.create_invoice(user.id, provider.name, 10_000)
    await payments.settle(provider.name, payment.invoice_id)
    await payments.settle(provider.name, payment.invoice_id)  # replay

    # REFERRAL_PERCENT defaults to 10%.
    assert (await wallet.get_balance(inviter.id)) == 1_000


async def test_expired_invoices_are_closed(session, payments, provider, user):
    from datetime import datetime, timedelta

    payment = await payments.create_invoice(user.id, provider.name, 50_000)
    payment.expires_at = datetime.utcnow() - timedelta(minutes=1)
    await session.commit()

    assert await payments.expire_stale() == 1
    await session.refresh(payment)
    assert payment.status == PaymentStatus.EXPIRED
