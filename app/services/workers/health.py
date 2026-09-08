"""Watches provider reachability and our upstream balance, alerting admins."""

from __future__ import annotations

from aiogram import Bot

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.money import format_money, to_minor
from app.providers.base import BaseSMSProvider
from app.services.notifications import NotificationService
from app.services.workers.base import BaseWorker

logger = get_logger(__name__)

class HealthWorker(BaseWorker):
    """Watches provider health and our upstream balance, alerting admins."""

    name = "health_worker"

    def __init__(
        self,
        sms_provider: BaseSMSProvider,
        notifications: NotificationService,
        settings: Settings,
        bot: Bot,
        interval: int = 600,
    ) -> None:
        super().__init__(interval)
        self._provider = sms_provider
        self._notifications = notifications
        self._settings = settings
        self._bot = bot
        self._alerted_down = False
        self._alerted_low_balance = False

    async def tick(self) -> int | None:
        try:
            balance = await self._provider.get_balance()
        except Exception as exc:
            if not self._alerted_down:
                self._alerted_down = True
                await self._notifications.notify_admins(
                    f"🚨 <b>Provider unavailable</b>\n\n{self._provider.name}: {exc}"
                )
            logger.error("health.provider_down", provider=self._provider.name, error=str(exc))
            return None

        if self._alerted_down:
            self._alerted_down = False
            await self._notifications.notify_admins(
                f"✅ <b>Provider recovered</b>\n\n{self._provider.name} is answering again."
            )

        threshold = to_minor(self._settings.sms_provider_low_balance_threshold)
        if threshold and balance < threshold:
            if not self._alerted_low_balance:
                self._alerted_low_balance = True
                await self._notifications.notify_admins(
                    "⚠️ <b>Low provider balance</b>\n\n"
                    f"Current: {format_money(balance, self._settings.currency_symbol)}\n"
                    f"Threshold: {format_money(threshold, self._settings.currency_symbol)}"
                )
        else:
            self._alerted_low_balance = False
        return None
