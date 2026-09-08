"""Activations, rentals and SMM orders."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select

from app.core.constants import (
    OrderKind,
    OrderStatus,
)
from app.database.models import (
    Order,
)
from app.database.repositories.base import BaseRepository


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
