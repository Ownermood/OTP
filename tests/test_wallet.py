"""Wallet invariants: auditable, atomic, exactly-once.

These are the tests that stand between the bot and double-charging a user.
"""

import asyncio

import pytest

from app.core.constants import TransactionType
from app.core.exceptions import InsufficientBalanceError
from app.database.repositories import TransactionRepository


async def test_credit_records_an_audit_trail(session, wallet, user):
    change = await wallet.credit(user.id, 5_000, TransactionType.DEPOSIT, "deposit:test:1")
    await session.commit()

    assert change.applied
    assert change.balance_before == 10_000
    assert change.balance_after == 15_000

    transactions = await TransactionRepository(session).list_for_user(user.id)
    assert len(transactions) == 1
    record = transactions[0]
    assert record.amount == 5_000
    assert record.balance_before == 10_000
    assert record.balance_after == 15_000
    assert record.type == TransactionType.DEPOSIT


async def test_debit_reduces_balance(session, wallet, user):
    change = await wallet.debit(user.id, 2_500, TransactionType.PURCHASE, "purchase:order:1")
    await session.commit()

    assert change.balance_after == 7_500
    assert (await wallet.get_balance(user.id)) == 7_500


async def test_debit_refuses_to_go_negative(session, wallet, user):
    with pytest.raises(InsufficientBalanceError):
        await wallet.debit(user.id, 20_000, TransactionType.PURCHASE, "purchase:order:2")

    assert (await wallet.get_balance(user.id)) == 10_000


async def test_replayed_credit_does_not_pay_twice(session, wallet, user):
    """The core payment-webhook guarantee."""
    key = "deposit:cryptobot:INVOICE-42"

    first = await wallet.credit(user.id, 5_000, TransactionType.DEPOSIT, key)
    second = await wallet.credit(user.id, 5_000, TransactionType.DEPOSIT, key)
    await session.commit()

    assert first.applied is True
    assert second.applied is False
    assert (await wallet.get_balance(user.id)) == 15_000
    assert len(await TransactionRepository(session).list_for_user(user.id)) == 1


async def test_replayed_debit_does_not_charge_twice(session, wallet, user):
    """The core double-click guarantee at the wallet level."""
    key = "purchase:order:99"

    first = await wallet.debit(user.id, 1_200, TransactionType.PURCHASE, key)
    second = await wallet.debit(user.id, 1_200, TransactionType.PURCHASE, key)
    await session.commit()

    assert first.applied is True
    assert second.applied is False
    assert (await wallet.get_balance(user.id)) == 8_800


async def test_refund_is_keyed_to_the_order(session, wallet, user):
    """A cancel handler and the poller can both try; only one refund lands."""
    await wallet.debit(user.id, 3_000, TransactionType.PURCHASE, "purchase:order:7")

    first = await wallet.refund(user.id, 3_000, order_id=7)
    second = await wallet.refund(user.id, 3_000, order_id=7)
    await session.commit()

    assert first.applied is True
    assert second.applied is False
    assert (await wallet.get_balance(user.id)) == 10_000


async def test_concurrent_identical_credits_settle_once(session_factory, session):
    """Two coroutines racing on the same key must not both credit.

    The pre-check can pass in both, so the unique index is what has to hold.
    """
    from app.database.models import User
    from app.services.wallet import WalletService

    session.add(User(id=2002, username="racer", balance=0))
    await session.commit()

    async def credit_once():
        async with session_factory() as own_session:
            outcome = await WalletService(own_session).credit(
                2002, 1_000, TransactionType.DEPOSIT, "deposit:race:1"
            )
            await own_session.commit()
            return outcome.applied

    results = await asyncio.gather(*(credit_once() for _ in range(4)), return_exceptions=True)
    applied = [r for r in results if r is True]

    assert len(applied) == 1, f"expected exactly one credit, got {results}"

    async with session_factory() as check:
        assert (await WalletService(check).get_balance(2002)) == 1_000


async def test_purchase_updates_lifetime_spend(session, wallet, user):
    await wallet.debit(user.id, 2_000, TransactionType.PURCHASE, "purchase:order:11")
    await session.commit()
    await session.refresh(user)

    assert user.total_spent == 2_000


async def test_referral_credit_tracks_lifetime_earnings(session, wallet, user):
    await wallet.credit(user.id, 400, TransactionType.REFERRAL, "referral:payment:3")
    await session.commit()
    await session.refresh(user)

    assert user.referral_earned == 400
    assert user.balance == 10_400


async def test_user_field_writes_are_visible_to_a_later_read(session, user):
    """Regression: a bare UPDATE left an already-loaded user holding old data."""
    from app.database.repositories import UserRepository

    users = UserRepository(session)
    await users.set_banned(user.id, True, "spam")
    await users.set_notifications(user.id, False)
    await users.set_pending_promo(user.id, 7)

    # Same session, same identity-mapped instance the admin screen would re-read.
    reread = await users.get(user.id)
    assert reread.is_banned is True
    assert reread.ban_reason == "spam"
    assert reread.notifications_enabled is False
    assert reread.pending_promo_id == 7
