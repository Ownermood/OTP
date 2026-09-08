"""Wallet.

Every rupee that moves passes through here, and every movement writes a
:class:`~app.database.models.Transaction`. Three properties hold:

* **Auditable** -- balance is never updated without a matching transaction row
  recording the before and after values.
* **Atomic** -- the caller's session is committed once, so a debit plus the
  order it pays for either both land or neither does.
* **Exactly-once** -- every movement carries an ``idempotency_key``. Replaying
  the same credit or refund is a no-op rather than a double payout.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TransactionType
from app.core.exceptions import InsufficientBalanceError
from app.core.logging import get_logger
from app.database.repositories import TransactionRepository, UserRepository

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BalanceChange:
    """Outcome of a wallet operation."""

    balance_before: int
    balance_after: int
    #: False when the idempotency key had already been used and nothing moved.
    applied: bool


class WalletService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._transactions = TransactionRepository(session)

    async def credit(
        self,
        user_id: int,
        amount: int,
        type_: TransactionType,
        idempotency_key: str,
        reference: str | None = None,
        description: str | None = None,
    ) -> BalanceChange:
        """Add ``amount`` minor units. Safe to call twice with the same key."""
        if amount <= 0:
            raise ValueError("credit amount must be positive")
        return await self._move(
            user_id, amount, type_, idempotency_key, reference, description
        )

    async def debit(
        self,
        user_id: int,
        amount: int,
        type_: TransactionType,
        idempotency_key: str,
        reference: str | None = None,
        description: str | None = None,
    ) -> BalanceChange:
        """Remove ``amount`` minor units, refusing to go negative."""
        if amount <= 0:
            raise ValueError("debit amount must be positive")
        return await self._move(
            user_id, -amount, type_, idempotency_key, reference, description
        )

    async def refund(
        self, user_id: int, amount: int, order_id: int, description: str | None = None
    ) -> BalanceChange:
        """Return money for an order.

        The key is derived from the order, so a cancel handler, the SMS poller
        and an admin can all attempt the same refund and only one lands.
        """
        return await self.credit(
            user_id,
            amount,
            TransactionType.REFUND,
            idempotency_key=f"refund:order:{order_id}",
            reference=f"order #{order_id}",
            description=description,
        )

    async def get_balance(self, user_id: int) -> int:
        user = await self._users.get(user_id)
        return user.balance if user else 0

    async def _move(
        self,
        user_id: int,
        signed_amount: int,
        type_: TransactionType,
        idempotency_key: str,
        reference: str | None,
        description: str | None,
    ) -> BalanceChange:
        user = await self._users.lock_for_update(user_id)
        if user is None:
            raise InsufficientBalanceError(f"unknown user {user_id}")

        # Fast path: the key is already spent, so this is a replay.
        if await self._transactions.exists(idempotency_key):
            logger.info("wallet.replay_ignored", user_id=user_id, key=idempotency_key)
            return BalanceChange(user.balance, user.balance, applied=False)

        balance_before = user.balance
        balance_after = balance_before + signed_amount
        if balance_after < 0:
            raise InsufficientBalanceError(
                "balance too low", required=-signed_amount, available=balance_before
            )

        try:
            # A SAVEPOINT so losing the race below rolls back only this insert,
            # leaving the caller's surrounding transaction intact.
            async with self._session.begin_nested():
                await self._transactions.create(
                    user_id=user_id,
                    type_=type_,
                    amount=signed_amount,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    idempotency_key=idempotency_key,
                    reference=reference,
                    description=description,
                )
        except IntegrityError:
            # Another coroutine inserted the same key between our check and our
            # insert. The unique index is the real guarantee; this is the race.
            logger.info("wallet.replay_raced", user_id=user_id, key=idempotency_key)
            return BalanceChange(balance_before, balance_before, applied=False)

        user.balance = balance_after
        if signed_amount < 0 and type_ is TransactionType.PURCHASE:
            await self._users.add_spent(user_id, -signed_amount)
        if signed_amount > 0 and type_ is TransactionType.REFERRAL:
            await self._users.add_referral_earned(user_id, signed_amount)

        await self._session.flush()
        logger.info(
            "wallet.moved",
            user_id=user_id,
            type=type_.value,
            amount=signed_amount,
            balance_after=balance_after,
        )
        return BalanceChange(balance_before, balance_after, applied=True)
