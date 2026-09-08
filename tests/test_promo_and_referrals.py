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
