"""User accounts, balances, bans and admin user search."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select

from app.core.constants import (
    PaymentStatus,
)
from app.database.models import (
    Order,
    Payment,
    User,
)
from app.database.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(
            select(User).where(func.lower(User.username) == username.lower())
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self, user_id: int, username: str | None, full_name: str | None
    ) -> tuple[User, bool]:
        """Fetch a user, creating them on first contact. Returns ``(user, created)``."""
        user = await self.get(user_id)
        if user is not None:
            # Usernames are reassignable on Telegram, so keep ours in sync.
            user.username = username
            user.full_name = full_name
            user.last_seen_at = datetime.utcnow()
            await self.session.flush()
            return user, False

        user = User(id=user_id, username=username, full_name=full_name)
        self.session.add(user)
        await self.session.flush()
        return user, True

    async def lock_for_update(self, user_id: int) -> User | None:
        """Read a user with a row lock so concurrent balance writes serialise.

        SQLite serialises writers anyway; the ``FOR UPDATE`` matters once the
        deployment moves to Postgres via ``DATABASE_URL``.
        """
        dialect = self.session.bind.dialect.name if self.session.bind else "sqlite"
        statement = select(User).where(User.id == user_id)
        if dialect != "sqlite":
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def add_spent(self, user_id: int, amount: int) -> None:
        await self._mutate(user_id, total_spent=lambda user: user.total_spent + amount)

    async def add_referral_earned(self, user_id: int, amount: int) -> None:
        await self._mutate(user_id, referral_earned=lambda user: user.referral_earned + amount)

    async def set_banned(self, user_id: int, banned: bool, reason: str | None = None) -> None:
        await self._mutate(user_id, is_banned=banned, ban_reason=reason)

    async def set_language(self, user_id: int, language: str) -> None:
        await self._mutate(user_id, language=language)

    async def set_pending_promo(self, user_id: int, promo_id: int | None) -> None:
        await self._mutate(user_id, pending_promo_id=promo_id)

    async def set_notifications(self, user_id: int, enabled: bool) -> None:
        await self._mutate(user_id, notifications_enabled=enabled)

    async def _mutate(self, user_id: int, **changes) -> None:
        """Apply field changes through the ORM object.

        A bare UPDATE statement would leave an already-loaded instance in this
        session holding the old value, so a caller that re-reads the user in
        the same request would see stale data. Callables receive the user and
        return the new value, which is how the counters increment.
        """
        user = await self.get(user_id)
        if user is None:
            return
        for field, value in changes.items():
            setattr(user, field, value(user) if callable(value) else value)
        await self.session.flush()

    async def search(self, query: str, limit: int = 10) -> Sequence[User]:
        """Admin search by numeric id or (partial) username."""
        term = query.strip().lstrip("@")
        conditions = [User.username.ilike(f"%{term}%")]
        if term.isdigit():
            conditions.append(User.id == int(term))
        result = await self.session.execute(
            select(User).where(or_(*conditions)).limit(limit)
        )
        return result.scalars().all()

    async def count(self) -> int:
        return int(await self.session.scalar(select(func.count(User.id))) or 0)

    async def count_active_since(self, since: datetime) -> int:
        return int(
            await self.session.scalar(
                select(func.count(User.id)).where(User.last_seen_at >= since)
            )
            or 0
        )

    async def count_new_since(self, since: datetime) -> int:
        return int(
            await self.session.scalar(select(func.count(User.id)).where(User.created_at >= since))
            or 0
        )

    async def ids_for_broadcast(self, audience: str) -> Sequence[int]:
        """Resolve a broadcast audience name to user ids."""
        statement = select(User.id).where(User.is_banned.is_(False))
        if audience == "active":
            statement = statement.where(User.last_seen_at >= datetime.utcnow() - timedelta(days=7))
        elif audience == "paying":
            paid = select(Payment.user_id).where(Payment.status == PaymentStatus.PAID)
            statement = statement.where(User.id.in_(paid))
        elif audience == "with_orders":
            statement = statement.where(User.id.in_(select(Order.user_id)))
        result = await self.session.execute(statement)
        return result.scalars().all()
