"""The admin audit log and runtime settings an admin can flip."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from app.core.constants import (
    AdminRole,
)
from app.database.models import (
    AdminAction,
    Setting,
)
from app.database.repositories.base import BaseRepository


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
