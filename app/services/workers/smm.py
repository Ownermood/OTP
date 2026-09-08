"""Polls open SMM orders for delivery progress."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.core.constants import OrderStatus
from app.core.logging import get_logger
from app.providers.base import BaseSMMProvider
from app.services.notifications import NotificationService
from app.services.workers.base import IDLE_INTERVAL, BaseWorker

logger = get_logger(__name__)

class SmmWorker(BaseWorker):
    """Polls open SMM orders for delivery progress."""

    name = "smm_worker"

    def __init__(
        self,
        session_factory: async_sessionmaker,
        provider: BaseSMMProvider,
        notifications: NotificationService,
        settings: Settings,
        renderer,
    ) -> None:
        super().__init__(settings.smm_poll_interval)
        self._session_factory = session_factory
        self._provider = provider
        self._notifications = notifications
        self._settings = settings
        self._render = renderer

    async def tick(self) -> int | None:
        from app.services.pricing import PricingService
        from app.services.smm import SmmService
        from app.services.wallet import WalletService

        async with self._session_factory() as session:
            service = SmmService(
                session,
                self._provider,
                PricingService(self._settings),
                WalletService(session),
                self._settings,
            )
            orders = list(await service.open_orders())
            if not orders:
                return IDLE_INTERVAL

            for order in orders:
                previous = OrderStatus(order.status)
                try:
                    await service.refresh_status(order)
                except Exception as exc:
                    logger.warning("smm.poll_failed", order_id=order.id, error=str(exc))
                    continue
                if OrderStatus(order.status) != previous and OrderStatus(order.status).is_final:
                    await self._notifications.notify_user(
                        order.user_id, self._render("smm.finished", order=order), essential=True
                    )
        return None
