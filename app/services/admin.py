"""Admin operations: analytics, user management, audit logging, health.

Every privileged action here writes an :class:`AdminAction` row, and every
balance adjustment goes through the wallet so it appears in the user's own
transaction history too. Nothing modifies a balance silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    ROLE_PERMISSIONS,
    AdminRole,
    OrderStatus,
    TransactionType,
)
from app.core.exceptions import AccessDeniedError, ValidationError
from app.core.logging import get_logger
from app.database.repositories import (
    AdminActionRepository,
    OrderRepository,
    PaymentRepository,
    SettingRepository,
    TransactionRepository,
    UserRepository,
)
from app.services.wallet import WalletService

logger = get_logger(__name__)

MAINTENANCE_KEY = "maintenance_mode"


def can(role: AdminRole | None, permission: str) -> bool:
    """Server-side permission check. Callback data never decides this."""
    return role is not None and permission in ROLE_PERMISSIONS[role]


def require(role: AdminRole | None, permission: str) -> None:
    if not can(role, permission):
        raise AccessDeniedError(f"role {role} lacks {permission}")


@dataclass(frozen=True, slots=True)
class Dashboard:
    """Everything the admin dashboard shows, for one time window."""

    users_total: int
    users_new: int
    users_active: int
    orders: int
    orders_success: int
    orders_failed: int
    revenue: int
    deposits: int
    refunds: int
    top_services: list[tuple[str, int]]
    top_countries: list[tuple[str, int]]

    @property
    def conversion(self) -> float:
        return (self.orders_success / self.orders * 100) if self.orders else 0.0

    @property
    def average_order(self) -> int:
        return self.revenue // self.orders_success if self.orders_success else 0


class AdminService:
    def __init__(self, session: AsyncSession, wallet: WalletService) -> None:
        self._session = session
        self._wallet = wallet
        self._users = UserRepository(session)
        self._orders = OrderRepository(session)
        self._payments = PaymentRepository(session)
        self._transactions = TransactionRepository(session)
        self._actions = AdminActionRepository(session)
        self._settings = SettingRepository(session)

    # -- analytics ------------------------------------------------------

    async def dashboard(self, days: int = 1) -> Dashboard:
        since = datetime.utcnow() - timedelta(days=days)
        return Dashboard(
            users_total=await self._users.count(),
            users_new=await self._users.count_new_since(since),
            users_active=await self._users.count_active_since(since),
            orders=await self._orders.count_since(since),
            orders_success=await self._orders.count_since(since, OrderStatus.SUCCESS),
            orders_failed=await self._orders.count_since(since, OrderStatus.FAILED),
            revenue=await self._orders.revenue_since(since),
            deposits=await self._payments.deposits_since(since),
            refunds=abs(await self._transactions.sum_since(TransactionType.REFUND, since)),
            top_services=list(await self._orders.top_services(since)),
            top_countries=list(await self._orders.top_countries(since)),
        )

    # -- users ----------------------------------------------------------

    async def search_users(self, query: str):
        return await self._users.search(query)

    async def search_orders(self, query: str):
        return await self._orders.search(query)

    async def search_payments(self, query: str):
        return await self._payments.search(query)

    async def adjust_balance(
        self, admin_id: int, role: AdminRole, user_id: int, amount: int, reason: str
    ) -> int:
        """Add (positive) or remove (negative) balance, with a full audit trail."""
        require(role, "balance")
        if amount == 0:
            raise ValidationError("adjustment must be non-zero")

        # Timestamped key: a deliberate repeat adjustment is allowed, an
        # accidental double-tap within the same second is not.
        key = f"admin:{admin_id}:{user_id}:{amount}:{int(datetime.utcnow().timestamp())}"
        if amount > 0:
            change = await self._wallet.credit(
                user_id, amount, TransactionType.ADMIN_ADJUSTMENT, key, f"admin {admin_id}", reason
            )
        else:
            change = await self._wallet.debit(
                user_id, -amount, TransactionType.ADMIN_ADJUSTMENT, key, f"admin {admin_id}", reason
            )
        await self._actions.log(
            admin_id, role, "balance_adjust", str(user_id), f"{amount} — {reason}"
        )
        await self._session.commit()
        return change.balance_after

    async def set_banned(
        self, admin_id: int, role: AdminRole, user_id: int, banned: bool, reason: str = ""
    ) -> None:
        require(role, "ban")
        await self._users.set_banned(user_id, banned, reason or None)
        await self._actions.log(
            admin_id, role, "ban" if banned else "unban", str(user_id), reason
        )
        await self._session.commit()

    async def user_detail(self, user_id: int):
        user = await self._users.get(user_id)
        if user is None:
            return None
        orders = await self._orders.list_for_user(user_id, limit=1000)
        return user, orders

    # -- orders / payments ----------------------------------------------

    async def list_orders(self, status: OrderStatus | None = None):
        return await self._orders.list_filtered(status=status)

    async def list_payments(self, status=None):
        return await self._payments.list_filtered(status=status)

    # -- settings / audit -----------------------------------------------

    async def is_maintenance(self, default: bool) -> bool:
        return await self._settings.get_bool(MAINTENANCE_KEY, default)

    async def set_maintenance(self, admin_id: int, role: AdminRole, enabled: bool) -> None:
        require(role, "maintenance")
        await self._settings.set(MAINTENANCE_KEY, "true" if enabled else "false")
        await self._actions.log(admin_id, role, "maintenance", None, str(enabled))
        await self._session.commit()

    async def audit_log(self, limit: int = 20):
        return await self._actions.recent(limit)

    async def log(
        self, admin_id: int, role: AdminRole, action: str, target: str | None = None,
        details: str | None = None,
    ) -> None:
        await self._actions.log(admin_id, role, action, target, details)
        await self._session.commit()

    async def broadcast_audience(self, audience: str):
        return await self._users.ids_for_broadcast(audience)
