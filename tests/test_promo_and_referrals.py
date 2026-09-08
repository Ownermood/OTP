"""Promo redemption and referral linking."""

import pytest

from app.core.exceptions import PromoError
from app.services.promo import PromoService
from app.services.referrals import ReferralService


@pytest.fixture
def promo(session, wallet) -> PromoService:
    return PromoService(session, wallet)


async def _make_promo(promo: PromoService, **overrides):
    payload = dict(
        code="WELCOME50",
        amount=5_000,
        max_activations=2,
        expires_at=None,
        min_deposit=0,
        created_by=1,
    )
    payload.update(overrides)
    return await promo.create(**payload)


async def test_redeem_credits_the_bonus(promo, user, wallet):
    await _make_promo(promo)
    redemption = await promo.redeem(user.id, "WELCOME50")

    assert redemption.amount == 5_000
    assert (await wallet.get_balance(user.id)) == 15_000


async def test_code_is_case_insensitive(promo, user):
    await _make_promo(promo)
    assert (await promo.redeem(user.id, "welcome50")).code == "WELCOME50"


async def test_same_user_cannot_redeem_twice(promo, user, wallet):
    await _make_promo(promo)
    await promo.redeem(user.id, "WELCOME50")

    with pytest.raises(PromoError):
        await promo.redeem(user.id, "WELCOME50")

    assert (await wallet.get_balance(user.id)) == 15_000


async def test_activation_limit_is_enforced(session, promo, user):
    from app.database.models import User

    await _make_promo(promo, max_activations=1)
    session.add(User(id=6006, username="second", balance=0))
    await session.commit()

    await promo.redeem(user.id, "WELCOME50")
    with pytest.raises(PromoError):
        await promo.redeem(6006, "WELCOME50")


async def test_expired_code_is_rejected(promo, user):
    from datetime import datetime, timedelta

    await _make_promo(promo, expires_at=datetime.utcnow() - timedelta(days=1))
    with pytest.raises(PromoError):
        await promo.redeem(user.id, "WELCOME50")


async def test_disabled_code_is_rejected(promo, user):
    created = await _make_promo(promo)
    await promo.set_active(created.id, False)

    with pytest.raises(PromoError):
        await promo.redeem(user.id, "WELCOME50")


async def test_unknown_code_is_rejected(promo, user):
    with pytest.raises(PromoError):
        await promo.redeem(user.id, "NOPE")


async def test_self_referral_is_blocked(session, wallet, settings, user):
    referrals = ReferralService(session, wallet, settings)
    assert await referrals.link(user.id, user.id) is False


async def test_a_user_can_only_be_invited_once(session, wallet, settings, user):
    from app.database.models import User

    session.add_all(
        [User(id=7007, username="a", balance=0), User(id=8008, username="b", balance=0)]
    )
    await session.commit()

    referrals = ReferralService(session, wallet, settings)
    assert await referrals.link(7007, user.id) is True
    assert await referrals.link(8008, user.id) is False


@pytest.mark.parametrize(
    ("payload", "expected"), [("ref123", 123), ("ref", None), ("nope", None), ("refabc", None)]
)
def test_start_payload_parsing(payload, expected):
    assert ReferralService.parse_start_payload(payload) == expected


# -- percent-of-deposit promos ---------------------------------------------


async def test_percent_promo_is_armed_not_paid_immediately(promo, user, wallet):
    """There is nothing to take a percentage of until a deposit arrives."""
    await _make_promo(promo, code="BOOST10", amount=0, percent=10)

    redemption = await promo.redeem(user.id, "BOOST10")

    assert redemption.deferred is True
    assert redemption.percent == 10
    assert (await wallet.get_balance(user.id)) == 10_000  # unchanged


async def test_percent_promo_pays_on_the_next_deposit(session, promo, user, wallet):
    await _make_promo(promo, code="BOOST10", amount=0, percent=10)
    await promo.redeem(user.id, "BOOST10")

    bonus = await promo.apply_deposit_bonus(user.id, deposit=50_000, payment_id=1)
    await session.commit()

    assert bonus == 5_000
    assert (await wallet.get_balance(user.id)) == 15_000


async def test_deposit_bonus_is_paid_once_per_payment(session, promo, user, wallet):
    """A replayed settlement must not pay the bonus twice."""
    await _make_promo(promo, code="BOOST10", amount=0, percent=10)
    await promo.redeem(user.id, "BOOST10")

    first = await promo.apply_deposit_bonus(user.id, 50_000, payment_id=1)
    second = await promo.apply_deposit_bonus(user.id, 50_000, payment_id=1)
    await session.commit()

    assert first == 5_000
    assert second == 0
    assert (await wallet.get_balance(user.id)) == 15_000


async def test_promo_is_disarmed_after_it_pays(session, promo, user, wallet):
    """A second, later deposit must not earn the bonus again."""
    await _make_promo(promo, code="BOOST10", amount=0, percent=10)
    await promo.redeem(user.id, "BOOST10")

    await promo.apply_deposit_bonus(user.id, 50_000, payment_id=1)
    await session.commit()
    later = await promo.apply_deposit_bonus(user.id, 50_000, payment_id=2)
    await session.commit()

    assert later == 0
    assert (await wallet.get_balance(user.id)) == 15_000


async def test_deposit_below_the_minimum_leaves_the_promo_armed(session, promo, user, wallet):
    await _make_promo(promo, code="BIG20", amount=0, percent=20, min_deposit=10_000)
    await promo.redeem(user.id, "BIG20")

    small = await promo.apply_deposit_bonus(user.id, 5_000, payment_id=1)
    await session.commit()
    assert small == 0

    # Still armed, so a qualifying deposit later still earns it.
    big = await promo.apply_deposit_bonus(user.id, 20_000, payment_id=2)
    await session.commit()
    assert big == 4_000


async def test_deposit_bonus_is_a_no_op_without_a_promo(session, promo, user, wallet):
    assert await promo.apply_deposit_bonus(user.id, 50_000, payment_id=1) == 0
    assert (await wallet.get_balance(user.id)) == 10_000


async def test_a_promo_needs_an_amount_or_a_percentage(promo):
    with pytest.raises(PromoError):
        await _make_promo(promo, code="EMPTY", amount=0, percent=0)


async def test_percent_promo_pays_through_a_real_settlement(
    session, user, wallet, settings, promo
):
    """End to end: redeem a percent code, then deposit, and see both credits."""
    from app.services.payments import PaymentService
    from app.services.referrals import ReferralService
    from tests.fakes import FakePaymentProvider

    provider = FakePaymentProvider()
    payments = PaymentService(
        session,
        {provider.name: provider},
        wallet,
        ReferralService(session, wallet, settings),
        settings,
        promo,
    )

    await _make_promo(promo, code="BOOST10", amount=0, percent=10)
    await promo.redeem(user.id, "BOOST10")

    payment = await payments.create_invoice(user.id, provider.name, 50_000)
    await payments.settle(provider.name, payment.invoice_id)
    await payments.settle(provider.name, payment.invoice_id)  # replay

    # 100.00 start + 500.00 deposit + 50.00 bonus.
    assert (await wallet.get_balance(user.id)) == 65_000
