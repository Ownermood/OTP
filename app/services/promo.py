"""Promo codes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TransactionType
from app.core.exceptions import PromoError
from app.core.logging import get_logger
from app.database.models import PromoCode
from app.database.repositories import PromoRepository
from app.services.wallet import WalletService

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Redemption:
    code: str
    amount: int
    balance_after: int


class PromoService:
    def __init__(self, session: AsyncSession, wallet: WalletService) -> None:
        self._session = session
        self._wallet = wallet
        self._promos = PromoRepository(session)

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
        if promo.amount <= 0:
            raise PromoError("code has no bonus configured")

        try:
            # The unique (promo_id, user_id) index turns a concurrent second
            # redemption into an IntegrityError rather than a second payout.
            async with self._session.begin_nested():
                await self._promos.record_usage(promo.id, user_id, promo.amount)
        except IntegrityError as exc:
            raise PromoError("already used by this user") from exc

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

    # -- admin ----------------------------------------------------------

    async def create(
        self,
        code: str,
        amount: int,
        max_activations: int,
        expires_at: datetime | None,
        min_deposit: int,
        created_by: int,
    ) -> PromoCode:
        if await self._promos.get_by_code(code) is not None:
            raise PromoError("code already exists")
        promo = await self._promos.create(
            code=code,
            amount=amount,
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
