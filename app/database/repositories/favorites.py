"""Saved service and country combinations."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select

from app.database.models import (
    Favorite,
)
from app.database.repositories.base import BaseRepository


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
