"""User profile, favourites, settings and balance transfers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.constants import OrderKind, TransactionType
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.database.models import User
from app.database.repositories import (
    FavoriteRepository,
    OrderRepository,
    TransactionRepository,
    UserRepository,
)
from app.services.wallet import WalletService

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ProfileStats:
    activations: int
    smm_orders: int
    total_spent: int
    referral_earned: int


class UserService:
    def __init__(self, session: AsyncSession, wallet: WalletService, settings: Settings) -> None:
        self._session = session
        self._wallet = wallet
        self._settings = settings
        self._users = UserRepository(session)
        self._orders = OrderRepository(session)
        self._favorites = FavoriteRepository(session)
        self._transactions = TransactionRepository(session)

    async def touch(
        self, user_id: int, username: str | None, full_name: str | None
    ) -> tuple[User, bool]:
        """Upsert the user on every interaction. Returns ``(user, is_new)``."""
        user, created = await self._users.get_or_create(user_id, username, full_name)
        await self._session.commit()
        return user, created

    async def get(self, user_id: int) -> User | None:
        return await self._users.get(user_id)

    async def stats(self, user_id: int) -> ProfileStats:
        counts = await self._orders.count_by_kind(user_id)
        user = await self._users.get(user_id)
        return ProfileStats(
            activations=counts.get(OrderKind.ACTIVATION, 0),
            smm_orders=counts.get(OrderKind.SMM, 0),
            total_spent=user.total_spent if user else 0,
            referral_earned=user.referral_earned if user else 0,
        )

    async def set_notifications(self, user_id: int, enabled: bool) -> None:
        await self._users.set_notifications(user_id, enabled)
        await self._session.commit()

    async def set_language(self, user_id: int, language: str) -> None:
        await self._users.set_language(user_id, language)
        await self._session.commit()

    # -- favourites -----------------------------------------------------

    async def add_favorite(
        self, user_id: int, service_code: str, service_name: str, country_id: int, country_name: str
    ) -> bool:
        favorite = await self._favorites.add(
            user_id, service_code, service_name, country_id, country_name
        )
        await self._session.commit()
        return favorite is not None

    async def list_favorites(self, user_id: int):
        return await self._favorites.list_for_user(user_id)

    async def get_favorite(self, favorite_id: int, user_id: int):
        return await self._favorites.get_owned(favorite_id, user_id)

    async def remove_favorite(self, favorite_id: int, user_id: int) -> bool:
        removed = await self._favorites.remove(favorite_id, user_id)
        await self._session.commit()
        return removed

    # -- wallet views ---------------------------------------------------

    async def transactions(self, user_id: int, types=None):
        return await self._transactions.list_for_user(user_id, types)

    async def transfer(self, from_user_id: int, to_username: str, amount: int) -> User:
        """Move balance between users atomically.

        Both legs share one transaction and one derived idempotency key pair, so
        a retried transfer cannot debit twice or credit twice.
        """
        if not self._settings.transfer_enabled:
            raise ValidationError("transfers are disabled")

        recipient = await self._users.get_by_username(to_username)
        if recipient is None:
            raise ValidationError("recipient not found")
        if recipient.id == from_user_id:
            raise ValidationError("cannot transfer to yourself")
        if recipient.is_banned:
            raise ValidationError("recipient is not available")

        # One key per transfer attempt, shared by both legs.
        transfer_key = f"transfer:{from_user_id}:{recipient.id}:{amount}:{_minute_bucket()}"
        await self._wallet.debit(
            from_user_id,
            amount,
            TransactionType.TRANSFER_OUT,
            idempotency_key=f"{transfer_key}:out",
            reference=f"@{to_username}",
            description="Balance transfer sent",
        )
        await self._wallet.credit(
            recipient.id,
            amount,
            TransactionType.TRANSFER_IN,
            idempotency_key=f"{transfer_key}:in",
            reference=str(from_user_id),
            description="Balance transfer received",
        )
        await self._session.commit()
        logger.info(
            "wallet.transfer", from_user=from_user_id, to_user=recipient.id, amount=amount
        )
        return recipient


def _minute_bucket() -> int:
    """Bucket transfers by the minute so an accidental double tap collapses."""
    from datetime import datetime

    return int(datetime.utcnow().timestamp() // 60)
