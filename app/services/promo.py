"""Promo codes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TransactionType
from app.core.exceptions import PromoError
from app.core.logging import get_logger
from app.core.money import apply_percent
from app.database.models import PromoCode
from app.database.repositories import PromoRepository, UserRepository
from app.services.wallet import WalletService

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Redemption:
    code: str
    amount: int
    balance_after: int
    #: True for a percent promo, whose bonus lands on the next deposit instead.
    deferred: bool = False
    percent: int = 0
    min_deposit: int = 0


class PromoService:
    def __init__(self, session: AsyncSession, wallet: WalletService) -> None:
        self._session = session
        self._wallet = wallet
        self._promos = PromoRepository(session)
        self._users = UserRepository(session)

    async def redeem(self, user_id: int, code: str) -> Redemption:
        """Redeem a code for its bonus. Raises :class:`PromoError` when invalid."""
        promo = await self._promos.get_by_code(code)
        if promo is None or not promo.is_active:
            raise PromoError("unknown or disabled code")
        if promo.expires_at is not None and promo.expires_at < datetime.utcnow():
            raise PromoError("code expired")
        if promo.used_count >= promo.max_activations:
            raise PromoError("activation limit reached")
        if await self._promos.has_used(promo.id, user_id):
            raise PromoError("already used by this user")
        if promo.amount <= 0 and promo.percent <= 0:
            raise PromoError("code has no bonus configured")

        try:
            # The unique (promo_id, user_id) index turns a concurrent second
            # redemption into an IntegrityError rather than a second payout.
            async with self._session.begin_nested():
                await self._promos.record_usage(promo.id, user_id, promo.amount)
        except IntegrityError as exc:
            raise PromoError("already used by this user") from exc

        # A percent promo has no amount until there is a deposit to take a
        # percentage of, so it is armed here and paid at settlement.
        if promo.percent > 0:
            await self._users.set_pending_promo(user_id, promo.id)
            await self._session.commit()
            logger.info(
                "promo.armed", user_id=user_id, code=promo.code, percent=promo.percent
            )
            return Redemption(
                promo.code,
                amount=0,
                balance_after=await self._wallet.get_balance(user_id),
                deferred=True,
                percent=promo.percent,
                min_deposit=promo.min_deposit,
            )

        change = await self._wallet.credit(
            user_id,
            promo.amount,
            TransactionType.PROMO,
            idempotency_key=f"promo:{promo.id}:{user_id}",
            reference=promo.code,
            description="Promo code bonus",
        )
        await self._session.commit()
        logger.info("promo.redeemed", user_id=user_id, code=promo.code, amount=promo.amount)
        return Redemption(promo.code, promo.amount, change.balance_after)

    async def apply_deposit_bonus(self, user_id: int, deposit: int, payment_id: int) -> int:
        """Pay an armed percent promo against a deposit. Returns the bonus paid.

        Keyed on the payment, so a replayed settlement cannot pay the bonus
        twice, and the promo is disarmed once it has been honoured.
        """
        user = await self._users.get(user_id)
        if user is None or user.pending_promo_id is None:
            return 0

        promo = await self._promos.get(user.pending_promo_id)
        if promo is None or not promo.is_active or promo.percent <= 0:
            await self._users.set_pending_promo(user_id, None)
            return 0
        if deposit < promo.min_deposit:
            # Too small to qualify; leave it armed for a future deposit.
            return 0

        bonus = apply_percent(deposit, promo.percent)
        if bonus <= 0:
            return 0

        change = await self._wallet.credit(
            user_id,
            bonus,
            TransactionType.PROMO,
            idempotency_key=f"promo:{promo.id}:payment:{payment_id}",
            reference=promo.code,
            description=f"Promo bonus ({promo.percent}% of deposit)",
        )
        if not change.applied:
            return 0

        await self._promos.settle_usage(promo.id, user_id, bonus)
        await self._users.set_pending_promo(user_id, None)
        logger.info(
            "promo.deposit_bonus_paid",
            user_id=user_id,
            code=promo.code,
            deposit=deposit,
            bonus=bonus,
        )
        return bonus

    # -- admin ----------------------------------------------------------

    async def create(
        self,
        code: str,
        amount: int,
        max_activations: int,
        expires_at: datetime | None,
        min_deposit: int,
        created_by: int,
        percent: int = 0,
    ) -> PromoCode:
        if await self._promos.get_by_code(code) is not None:
            raise PromoError("code already exists")
        if amount <= 0 and percent <= 0:
            raise PromoError("a promo needs either an amount or a percentage")
        promo = await self._promos.create(
            code=code,
            amount=amount,
            percent=percent,
            max_activations=max_activations,
            expires_at=expires_at,
            min_deposit=min_deposit,
            created_by=created_by,
        )
        await self._session.commit()
        return promo

    async def list_all(self):
        return await self._promos.list_all()

    async def set_active(self, promo_id: int, active: bool) -> None:
        await self._promos.set_active(promo_id, active)
        await self._session.commit()

    async def delete(self, promo_id: int) -> bool:
        deleted = await self._promos.delete(promo_id)
        await self._session.commit()
        return deleted
