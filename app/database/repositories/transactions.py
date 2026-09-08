"""The audit trail of every balance movement."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select

from app.core.constants import (
    TransactionType,
)
from app.database.models import (
    Transaction,
)
from app.database.repositories.base import BaseRepository


class TransactionRepository(BaseRepository):
    async def exists(self, idempotency_key: str) -> bool:
        result = await self.session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.idempotency_key == idempotency_key
            )
        )
        return bool(result.scalar_one())

    async def create(
        self,
        user_id: int,
        type_: TransactionType,
        amount: int,
        balance_before: int,
        balance_after: int,
        idempotency_key: str,
        reference: str | None = None,
        description: str | None = None,
    ) -> Transaction:
        transaction = Transaction(
            user_id=user_id,
            type=type_,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            idempotency_key=idempotency_key,
            reference=reference,
            description=description,
        )
        self.session.add(transaction)
        await self.session.flush()
        return transaction

    async def list_for_user(
        self, user_id: int, types: Sequence[TransactionType] | None = None, limit: int = 200
    ) -> Sequence[Transaction]:
        statement = select(Transaction).where(Transaction.user_id == user_id)
        if types:
            statement = statement.where(Transaction.type.in_(list(types)))
        result = await self.session.execute(
            statement.order_by(Transaction.created_at.desc()).limit(limit)
        )
        return result.scalars().all()

    async def sum_since(self, type_: TransactionType, since: datetime) -> int:
        return int(
            await self.session.scalar(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.type == type_, Transaction.created_at >= since
                )
            )
            or 0
        )
