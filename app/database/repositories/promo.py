"""Promo codes and their redemptions."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, select, update

from app.database.models import (
    PromoCode,
    PromoUsage,
)
from app.database.repositories.base import BaseRepository


class PromoRepository(BaseRepository):
    async def create(self, **values: Any) -> PromoCode:
        promo = PromoCode(**values)
        self.session.add(promo)
        await self.session.flush()
        return promo

    async def get_by_code(self, code: str) -> PromoCode | None:
        result = await self.session.execute(
            select(PromoCode).where(func.upper(PromoCode.code) == code.upper())
        )
        return result.scalar_one_or_none()

    async def get(self, promo_id: int) -> PromoCode | None:
        return await self.session.get(PromoCode, promo_id)


    async def list_all(self) -> Sequence[PromoCode]:
        result = await self.session.execute(
            select(PromoCode).order_by(PromoCode.created_at.desc())
        )
        return result.scalars().all()

    async def record_usage(self, promo_id: int, user_id: int, amount: int) -> PromoUsage:
        """Record a redemption and bump the counter in the same flush.

        The unique ``(promo_id, user_id)`` constraint makes a concurrent second
        redemption fail here rather than credit twice.
        """
        usage = PromoUsage(promo_id=promo_id, user_id=user_id, amount=amount)
        self.session.add(usage)
        await self.session.execute(
            update(PromoCode)
            .where(PromoCode.id == promo_id)
            .values(used_count=PromoCode.used_count + 1)
        )
        await self.session.flush()
        return usage

    async def settle_usage(self, promo_id: int, user_id: int, amount: int) -> None:
        """Fill in the amount of a usage that was recorded before it was known."""
        await self.session.execute(
            update(PromoUsage)
            .where(PromoUsage.promo_id == promo_id, PromoUsage.user_id == user_id)
            .values(amount=amount)
        )

    async def has_used(self, promo_id: int, user_id: int) -> bool:
        result = await self.session.execute(
            select(func.count(PromoUsage.id)).where(
                PromoUsage.promo_id == promo_id, PromoUsage.user_id == user_id
            )
        )
        return bool(result.scalar_one())

    async def set_active(self, promo_id: int, active: bool) -> None:
        await self.session.execute(
            update(PromoCode).where(PromoCode.id == promo_id).values(is_active=active)
        )

    async def delete(self, promo_id: int) -> bool:
        result = await self.session.execute(delete(PromoCode).where(PromoCode.id == promo_id))
        return bool(result.rowcount)
