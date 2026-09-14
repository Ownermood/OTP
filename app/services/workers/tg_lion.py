"""Polls open TG-Lion Telegram-number orders for their code.

Mirrors :mod:`app.services.workers.sms` -- same orphan sweep, same expiry
handling -- but through :class:`~app.services.telegram_numbers.TelegramNumberService`
instead of :class:`~app.services.orders.OrderService`, since TG-Lion is not a
:class:`~app.providers.base.BaseSMSProvider`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.keyboards.style import copy_keyboard
from app.core.config import Settings
from app.core.constants import OrderStatus
from app.core.logging import get_logger
from app.providers.tg_lion import TgLionProvider
from app.services.notifications import NotificationService
from app.services.workers.base import IDLE_INTERVAL, ORPHAN_GRACE_SECONDS, BaseWorker

logger = get_logger(__name__)


class TgLionWorker(BaseWorker):
    """Polls open Telegram-number orders for their code."""

    name = "tg_lion_worker"

    def __init__(
        self,
        session_factory: async_sessionmaker,
        provider: TgLionProvider,
        notifications: NotificationService,
        settings: Settings,
        renderer,
    ) -> None:
        super().__init__(settings.tg_lion_poll_interval)
        self._session_factory = session_factory
        self._provider = provider
        self._notifications = notifications
        self._settings = settings
        self._render = renderer

    async def tick(self) -> int | None:
        from app.core.constants import OrderKind
        from app.database.repositories import OrderRepository
        from app.services.pricing import PricingService
        from app.services.telegram_numbers import TelegramNumberService
        from app.services.wallet import WalletService

        async with self._session_factory() as session:
            orders = list(await OrderRepository(session).list_open(OrderKind.TELEGRAM))
            if not orders:
                return IDLE_INTERVAL

            wallet = WalletService(session)
            service = TelegramNumberService(
                session, self._provider, PricingService(self._settings), wallet, self._settings
            )

            for order in orders:
                if await self._sweep_orphan(service, order):
                    continue
                await self._poll(service, order)
        return None

    async def _sweep_orphan(self, service, order) -> bool:
        """Refund an order charged for but never reaching the provider.

        Same crash window as the SMS worker's own sweep: a process death
        between the wallet debit and the provider call.
        """
        if order.provider_order_id:
            return False
        if order.created_at > datetime.utcnow() - timedelta(seconds=ORPHAN_GRACE_SECONDS):
            return False

        await service.fail_orphan(order)
        await self._notifications.notify_user(
            order.user_id, self._render("telegram.failed", order=order), essential=True
        )
        return True

    async def _poll(self, service, order) -> None:
        if order.expires_at and order.expires_at < datetime.utcnow():
            await service.expire(order)
            await self._notifications.notify_user(
                order.user_id, self._render("telegram.expired", order=order), essential=True
            )
            return
        if not order.provider_order_id:
            return

        previous_status = order.status
        await service.refresh(order)
        if order.status == OrderStatus.SUCCESS and previous_status != OrderStatus.SUCCESS:
            await self._notifications.notify_user(
                order.user_id,
                self._render("telegram.received", order=order),
                reply_markup=copy_keyboard(order.phone, order.sms_code),
                essential=True,
            )
