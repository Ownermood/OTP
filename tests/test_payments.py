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


async def _age(session, payment, **delta):
    """Backdate an invoice's expiry, as if time had passed."""
    from datetime import datetime, timedelta

    payment.expires_at = datetime.utcnow() - timedelta(**delta)
    await session.commit()


async def test_a_just_expired_invoice_is_not_abandoned(session, payments, provider, user):
    """The gateway gets a grace window to report a payment made at the buzzer."""
    payment = await payments.create_invoice(user.id, provider.name, 50_000)
    await _age(session, payment, minutes=1)

    assert await payments.expire_stale() == 0
    await session.refresh(payment)
    assert payment.status == PaymentStatus.PENDING


async def test_an_invoice_past_the_grace_window_is_abandoned(session, payments, provider, user):
    payment = await payments.create_invoice(user.id, provider.name, 50_000)
    await _age(session, payment, hours=48)

    assert await payments.expire_stale() == 1
    await session.refresh(payment)
    assert payment.status == PaymentStatus.EXPIRED


async def test_a_lapsed_invoice_is_still_polled(session, payments, provider, user):
    """Regression: an invoice paid during a restart used to be written off.

    The poller filtered on expires_at, so an invoice that lapsed while the bot
    was down was marked expired and never checked again -- with the gateway
    already holding the user's money.
    """
    payment = await payments.create_invoice(user.id, provider.name, 50_000)
    await _age(session, payment, minutes=30)

    pending = await payments.get_pending(provider.name)
    assert [p.id for p in pending] == [payment.id]


async def test_a_late_payment_is_still_credited(session, payments, provider, user, wallet):
    """Money the gateway confirms late must reach the user, not be kept."""
    payment = await payments.create_invoice(user.id, provider.name, 50_000)
    await _age(session, payment, hours=48)
    await payments.expire_stale()
    await session.refresh(payment)
    assert payment.status == PaymentStatus.EXPIRED

    # The user taps Check Payment days later; the gateway now reports it paid.
    settlement = await payments.settle(provider.name, payment.invoice_id)

    assert settlement is not None
    assert settlement.credited is True
    assert (await wallet.get_balance(user.id)) == 60_000


async def test_a_late_payment_is_still_credited_only_once(session, payments, provider, user, wallet):
    payment = await payments.create_invoice(user.id, provider.name, 50_000)
    await _age(session, payment, hours=48)
    await payments.expire_stale()

    await payments.settle(provider.name, payment.invoice_id)
    await payments.settle(provider.name, payment.invoice_id)

    assert (await wallet.get_balance(user.id)) == 60_000


async def test_a_settled_payment_is_never_re_credited(session, payments, provider, user, wallet):
    """PAID is terminal: nothing reopens it, however it is replayed."""
    payment = await payments.create_invoice(user.id, provider.name, 50_000)
    await payments.settle(provider.name, payment.invoice_id)

    await _age(session, payment, hours=48)
    await payments.expire_stale()
    await payments.settle(provider.name, payment.invoice_id)

    await session.refresh(payment)
    assert payment.status == PaymentStatus.PAID
    assert (await wallet.get_balance(user.id)) == 60_000
