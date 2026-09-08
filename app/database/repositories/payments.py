"""Deposit invoices, gateway and manually reviewed alike."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select, update

from app.core.constants import (
    PaymentStatus,
)
from app.database.models import (
    Payment,
)
from app.database.repositories.base import BaseRepository


class PaymentRepository(BaseRepository):
    async def create(self, **values: Any) -> Payment:
        payment = Payment(**values)
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def get(self, payment_id: int) -> Payment | None:
        return await self.session.get(Payment, payment_id)

    async def get_by_invoice(self, provider: str, invoice_id: str) -> Payment | None:
        result = await self.session.execute(
            select(Payment).where(Payment.provider == provider, Payment.invoice_id == invoice_id)
        )
        return result.scalar_one_or_none()

    async def list_pending(self, provider: str, limit: int = 200) -> Sequence[Payment]:
        """Invoices the poller still has to resolve.

        Deliberately *not* filtered on ``expires_at``. A user can pay in the
        last seconds before an invoice lapses, and if the bot is restarting at
        that moment the payment would otherwise be written off unchecked while
        the gateway has already taken the money. Invoices are only abandoned
        once :meth:`expire_stale` has given the provider a long grace window to
        report them.
        """
        result = await self.session.execute(
            select(Payment)
            .where(Payment.provider == provider, Payment.status == PaymentStatus.PENDING)
            .order_by(Payment.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def count_pending_for_user(self, provider: str, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Payment.id)).where(
                Payment.provider == provider,
                Payment.user_id == user_id,
                Payment.status == PaymentStatus.PENDING,
            )
        )
        return int(result.scalar_one())

    async def expire_stale(self, grace_hours: int) -> int:
        """Abandon invoices the provider has not reported for ``grace_hours``.

        The grace period is measured past the invoice's own expiry, so a
        payment that landed late -- or while the bot was down -- still gets
        polled and credited before we stop asking about it.
        """
        cutoff = datetime.utcnow() - timedelta(hours=grace_hours)
        result = await self.session.execute(
            update(Payment)
            .where(
                Payment.status == PaymentStatus.PENDING,
                Payment.expires_at < cutoff,
                # Manually reviewed requests wait for a human, not a clock.
                Payment.provider != "manual",
            )
            .values(status=PaymentStatus.EXPIRED)
        )
        return int(result.rowcount or 0)

    async def list_for_user(self, user_id: int, limit: int = 100) -> Sequence[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def list_filtered(
        self, status: PaymentStatus | None = None, limit: int = 100
    ) -> Sequence[Payment]:
        statement = select(Payment)
        if status is not None:
            statement = statement.where(Payment.status == status)
        result = await self.session.execute(
            statement.order_by(Payment.created_at.desc()).limit(limit)
        )
        return result.scalars().all()

    async def search(self, query: str, limit: int = 10) -> Sequence[Payment]:
        term = query.strip()
        conditions = [Payment.invoice_id == term]
        if term.isdigit():
            conditions.append(Payment.id == int(term))
        result = await self.session.execute(
            select(Payment).where(or_(*conditions)).limit(limit)
        )
        return result.scalars().all()

    async def deposits_since(self, since: datetime) -> int:
        return int(
            await self.session.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.status == PaymentStatus.PAID, Payment.paid_at >= since
                )
            )
            or 0
        )
