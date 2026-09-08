"""Repositories.

All SQL lives here. Services compose repositories; handlers never touch a
session directly. Repositories flush but do not commit -- the caller owns the
transaction boundary, which is what lets a purchase debit the wallet and create
the order atomically.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    AdminRole,
    OrderKind,
    OrderStatus,
    PaymentStatus,
    TransactionType,
)
from app.database.models import (
    AdminAction,
    Favorite,
    Order,
    Payment,
    PromoCode,
    PromoUsage,
    Referral,
    Setting,
    Transaction,
    User,
)


class BaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


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


class OrderRepository(BaseRepository):
    async def create(self, **values: Any) -> Order:
        order = Order(**values)
        self.session.add(order)
        await self.session.flush()
        return order

    async def get(self, order_id: int) -> Order | None:
        return await self.session.get(Order, order_id)

    async def get_owned(self, order_id: int, user_id: int) -> Order | None:
        """Fetch an order only if ``user_id`` owns it.

        Every user-facing order lookup goes through this, so an order id from
        callback data can never expose someone else's order.
        """
        result = await self.session.execute(
            select(Order).where(Order.id == order_id, Order.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_provider_id(self, provider: str, provider_order_id: str) -> Order | None:
        result = await self.session.execute(
            select(Order).where(
                Order.provider == provider, Order.provider_order_id == provider_order_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: int, kind: OrderKind | None = None, limit: int = 200
    ) -> Sequence[Order]:
        statement = select(Order).where(Order.user_id == user_id)
        if kind is not None:
            statement = statement.where(Order.kind == kind)
        result = await self.session.execute(statement.order_by(Order.created_at.desc()).limit(limit))
        return result.scalars().all()

    async def list_open(self, kind: OrderKind) -> Sequence[Order]:
        """Orders the poller still needs to watch."""
        result = await self.session.execute(
            select(Order).where(
                Order.kind == kind,
                Order.status.in_([OrderStatus.PENDING, OrderStatus.PROCESSING]),
            )
        )
        return result.scalars().all()

    async def has_open_order(self, user_id: int, service_code: str, country_id: int | None) -> bool:
        """True when the user already has an identical activation in flight.

        This is the server-side half of double-click protection: even if two
        confirm callbacks slip past the token guard, the second one is rejected.
        """
        result = await self.session.execute(
            select(func.count(Order.id)).where(
                Order.user_id == user_id,
                Order.service_code == service_code,
                Order.country_id == country_id,
                Order.kind == OrderKind.ACTIVATION,
                Order.status.in_([OrderStatus.PENDING, OrderStatus.PROCESSING]),
            )
        )
        return bool(result.scalar_one())

    async def search(self, query: str, limit: int = 10) -> Sequence[Order]:
        """Admin search by internal id, provider order id or phone number."""
        term = query.strip().lstrip("#")
        conditions = [
            Order.provider_order_id == term,
            Order.phone.ilike(f"%{term}%"),
        ]
        if term.isdigit():
            conditions.append(Order.id == int(term))
        result = await self.session.execute(
            select(Order).where(or_(*conditions)).order_by(Order.created_at.desc()).limit(limit)
        )
        return result.scalars().all()

    async def list_filtered(
        self,
        status: OrderStatus | None = None,
        kind: OrderKind | None = None,
        limit: int = 100,
    ) -> Sequence[Order]:
        statement = select(Order)
        if status is not None:
            statement = statement.where(Order.status == status)
        if kind is not None:
            statement = statement.where(Order.kind == kind)
        result = await self.session.execute(statement.order_by(Order.created_at.desc()).limit(limit))
        return result.scalars().all()

    async def count_since(self, since: datetime, status: OrderStatus | None = None) -> int:
        statement = select(func.count(Order.id)).where(Order.created_at >= since)
        if status is not None:
            statement = statement.where(Order.status == status)
        return int(await self.session.scalar(statement) or 0)

    async def revenue_since(self, since: datetime) -> int:
        """Sum of prices for successful orders in the window, in minor units."""
        return int(
            await self.session.scalar(
                select(func.coalesce(func.sum(Order.price), 0)).where(
                    Order.created_at >= since, Order.status == OrderStatus.SUCCESS
                )
            )
            or 0
        )

    async def top_services(self, since: datetime, limit: int = 5) -> Sequence[tuple[str, int]]:
        result = await self.session.execute(
            select(Order.service_name, func.count(Order.id).label("n"))
            .where(Order.created_at >= since)
            .group_by(Order.service_name)
            .order_by(func.count(Order.id).desc())
            .limit(limit)
        )
        return [(row[0], int(row[1])) for row in result.all()]

    async def top_countries(self, since: datetime, limit: int = 5) -> Sequence[tuple[str, int]]:
        result = await self.session.execute(
            select(Order.country_name, func.count(Order.id).label("n"))
            .where(Order.created_at >= since, Order.country_name.is_not(None))
            .group_by(Order.country_name)
            .order_by(func.count(Order.id).desc())
            .limit(limit)
        )
        return [(row[0], int(row[1])) for row in result.all()]

    async def recently_used(self, user_id: int, limit: int = 5) -> Sequence[Order]:
        """Distinct service+country pairs the user bought most recently."""
        result = await self.session.execute(
            select(Order)
            .where(Order.user_id == user_id, Order.kind == OrderKind.ACTIVATION)
            .order_by(Order.created_at.desc())
            .limit(50)
        )
        seen: set[tuple[str, int | None]] = set()
        unique: list[Order] = []
        for order in result.scalars().all():
            key = (order.service_code, order.country_id)
            if key not in seen:
                seen.add(key)
                unique.append(order)
            if len(unique) >= limit:
                break
        return unique

    async def popular_services(self, limit: int = 8) -> Sequence[str]:
        since = datetime.utcnow() - timedelta(days=30)
        result = await self.session.execute(
            select(Order.service_code)
            .where(Order.created_at >= since, Order.kind == OrderKind.ACTIVATION)
            .group_by(Order.service_code)
            .order_by(func.count(Order.id).desc())
            .limit(limit)
        )
        return result.scalars().all()


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

    async def count_failed_since(self, since: datetime) -> int:
        return int(
            await self.session.scalar(
                select(func.count(Payment.id)).where(
                    Payment.status == PaymentStatus.FAILED, Payment.created_at >= since
                )
            )
            or 0
        )


class FavoriteRepository(BaseRepository):
    async def add(
        self, user_id: int, service_code: str, service_name: str, country_id: int, country_name: str
    ) -> Favorite | None:
        """Add a favourite, or return ``None`` when it already exists."""
        existing = await self.session.execute(
            select(Favorite).where(
                Favorite.user_id == user_id,
                Favorite.service_code == service_code,
                Favorite.country_id == country_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return None
        favorite = Favorite(
            user_id=user_id,
            service_code=service_code,
            service_name=service_name,
            country_id=country_id,
            country_name=country_name,
        )
        self.session.add(favorite)
        await self.session.flush()
        return favorite

    async def get_owned(self, favorite_id: int, user_id: int) -> Favorite | None:
        result = await self.session.execute(
            select(Favorite).where(Favorite.id == favorite_id, Favorite.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: int) -> Sequence[Favorite]:
        result = await self.session.execute(
            select(Favorite)
            .where(Favorite.user_id == user_id)
            .order_by(Favorite.created_at.desc())
        )
        return result.scalars().all()

    async def remove(self, favorite_id: int, user_id: int) -> bool:
        result = await self.session.execute(
            delete(Favorite).where(Favorite.id == favorite_id, Favorite.user_id == user_id)
        )
        return bool(result.rowcount)


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

    async def list_active(self) -> Sequence[PromoCode]:
        result = await self.session.execute(
            select(PromoCode).where(PromoCode.is_active.is_(True)).order_by(PromoCode.created_at.desc())
        )
        return result.scalars().all()

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


class AdminActionRepository(BaseRepository):
    async def log(
        self,
        admin_id: int,
        role: AdminRole,
        action: str,
        target: str | None = None,
        details: str | None = None,
    ) -> None:
        self.session.add(
            AdminAction(admin_id=admin_id, role=role, action=action, target=target, details=details)
        )
        await self.session.flush()

    async def recent(self, limit: int = 20) -> Sequence[AdminAction]:
        result = await self.session.execute(
            select(AdminAction).order_by(AdminAction.created_at.desc()).limit(limit)
        )
        return result.scalars().all()


class SettingRepository(BaseRepository):
    async def get(self, key: str, default: str | None = None) -> str | None:
        setting = await self.session.get(Setting, key)
        return setting.value if setting else default

    async def get_bool(self, key: str, default: bool = False) -> bool:
        value = await self.get(key)
        return default if value is None else value.lower() in {"1", "true", "yes", "on"}

    async def set(self, key: str, value: str) -> None:
        setting = await self.session.get(Setting, key)
        if setting is None:
            self.session.add(Setting(key=key, value=value))
        else:
            setting.value = value
        await self.session.flush()
