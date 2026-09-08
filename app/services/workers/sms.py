"""Polls activations for their SMS.

Also sweeps orders that were charged for but never reached the provider -- the
state a crash between the wallet debit and the provider call leaves behind.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.core.constants import OrderKind
from app.core.logging import get_logger
from app.providers.base import BaseSMSProvider
from app.services.notifications import NotificationService
from app.services.workers.base import (
    IDLE_INTERVAL,
    ORPHAN_GRACE_SECONDS,
    BaseWorker,
)

logger = get_logger(__name__)

class SmsWorker(BaseWorker):
    """Polls activations for their SMS."""

    name = "sms_worker"

    def __init__(
        self,
        session_factory: async_sessionmaker,
        provider: BaseSMSProvider,
        notifications: NotificationService,
        settings: Settings,
        renderer,
    ) -> None:
        super().__init__(settings.sms_poll_interval)
        self._session_factory = session_factory
        self._provider = provider
        self._notifications = notifications
        self._settings = settings
        self._render = renderer

    async def tick(self) -> int | None:
        # Imported here to keep the service layer free of circular imports.
        from app.database.repositories import OrderRepository
        from app.services.orders import OrderService
        from app.services.pricing import PricingService
        from app.services.wallet import WalletService

        async with self._session_factory() as session:
            orders = list(await OrderRepository(session).list_open(OrderKind.ACTIVATION))
            if not orders:
                return IDLE_INTERVAL

            wallet = WalletService(session)
            service = OrderService(
                session, self._provider, PricingService(self._settings), wallet, self._settings
            )

            for order in orders:
                if await self._sweep_orphan(service, order):
                    continue
                await self._poll_activation(service, order)
        return None

    async def _sweep_orphan(self, service, order) -> bool:
        """Refund an order that was charged for but never reached the provider.

        A crash between the wallet debit and the provider call leaves the order
        with no provider id and no expiry, so no other path would ever resolve
        it and the user stays charged for nothing. True when handled here.
        """
        if order.provider_order_id:
            return False
        if order.created_at > datetime.utcnow() - timedelta(seconds=ORPHAN_GRACE_SECONDS):
            # Still young enough that a purchase may be mid-flight right now.
            return False

        await service.fail_orphan(order)
        await self._notifications.notify_user(
            order.user_id, self._render("sms.failed", order=order), essential=True
        )
        return True

    async def _poll_activation(self, service, order) -> None:
        if order.expires_at and order.expires_at < datetime.utcnow():
            await service.expire(order)
            await self._notifications.notify_user(
                order.user_id, self._render("sms.expired", order=order), essential=True
            )
            return
        if not order.provider_order_id:
            return

        try:
            status = await self._provider.get_activation_status(order.provider_order_id)
        except Exception as exc:
            logger.warning("sms.poll_failed", order_id=order.id, error=str(exc))
            return

        if status.state == "received":
            await service.mark_sms_received(order, status.code, status.text)
            await self._notifications.notify_user(
                order.user_id,
                self._render("sms.received", order=order, code=status.code, text=status.text),
                essential=True,
            )
        elif status.state in ("cancelled", "expired"):
            await service.refund_provider_cancelled(order)
            await self._notifications.notify_user(
                order.user_id, self._render("sms.cancelled", order=order), essential=True
            )
