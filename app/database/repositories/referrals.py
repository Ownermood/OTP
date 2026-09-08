"""Who invited whom, and what they earned."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select, update

from app.database.models import (
    Referral,
)
from app.database.repositories.base import BaseRepository


class ReferralRepository(BaseRepository):
    async def link(self, inviter_id: int, invited_id: int) -> bool:
        """Record an invite. Returns False when it is self-referral or a repeat."""
        if inviter_id == invited_id:
            return False
        existing = await self.session.execute(
            select(func.count(Referral.id)).where(Referral.invited_id == invited_id)
        )
        if existing.scalar_one():
            return False
        self.session.add(Referral(inviter_id=inviter_id, invited_id=invited_id))
        await self.session.flush()
        return True

    async def get_inviter(self, invited_id: int) -> int | None:
        result = await self.session.execute(
            select(Referral.inviter_id).where(Referral.invited_id == invited_id)
        )
        return result.scalar_one_or_none()

    async def count_invited(self, inviter_id: int) -> int:
        return int(
            await self.session.scalar(
                select(func.count(Referral.id)).where(Referral.inviter_id == inviter_id)
            )
            or 0
        )

    async def add_earning(self, inviter_id: int, invited_id: int, amount: int) -> None:
        await self.session.execute(
            update(Referral)
            .where(Referral.inviter_id == inviter_id, Referral.invited_id == invited_id)
            .values(earned=Referral.earned + amount)
        )

    async def list_for_inviter(self, inviter_id: int, limit: int = 100) -> Sequence[Referral]:
        result = await self.session.execute(
            select(Referral)
            .where(Referral.inviter_id == inviter_id)
            .order_by(Referral.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
