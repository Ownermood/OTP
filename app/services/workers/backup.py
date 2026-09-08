"""Takes a scheduled backup and files it somewhere it will survive."""

from __future__ import annotations

from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.backup import BackupService
from app.services.notifications import NotificationService
from app.services.workers.base import BaseWorker

logger = get_logger(__name__)


class BackupWorker(BaseWorker):
    """Sends a snapshot to the backup destination on a schedule.

    The destination is a Telegram chat rather than the disk the database is
    already on: a backup that dies with the server is not a backup.
    """

    name = "backup_worker"

    def __init__(
        self,
        bot: Bot,
        backups: BackupService,
        notifications: NotificationService,
        settings: Settings,
    ) -> None:
        super().__init__(max(settings.backup_interval_hours, 1) * 3600)
        self._bot = bot
        self._backups = backups
        self._notifications = notifications
        self._settings = settings
        self._destination = settings.backup_chat_id or settings.admin_ids[0]
        self._last_alert: str | None = None

    async def tick(self) -> int | None:
        if not self._backups.supported:
            return None

        try:
            async with self._backups.snapshot() as (path, size):
                if self._backups.too_large(size):
                    await self._alert(
                        "backup.too_large",
                        f"⚠️ <b>Backup too large to send</b>\n\n"
                        f"{size / 1024 / 1024:.1f} MB exceeds Telegram's 50 MB limit. "
                        f"Copy <code>{self._settings.database_url}</code> off the server "
                        f"another way.",
                    )
                    return None

                await self._bot.send_document(
                    chat_id=self._destination,
                    document=FSInputFile(path, filename=path.name),
                    caption=(
                        f"💾 <b>Automatic backup</b>\n\n"
                        f"<code>{path.name}</code>\n"
                        f"{size / 1024 / 1024:.2f} MB · "
                        f"{datetime.utcnow():%d %b %Y %H:%M} UTC"
                    ),
                )
            logger.info("backup.scheduled_sent", destination=self._destination)
            self._last_alert = None
        except TelegramAPIError as exc:
            # A backup nobody receives is the same as no backup, so this is
            # said out loud rather than left in the log.
            await self._alert(
                "backup.delivery_failed",
                f"🚨 <b>Backup could not be delivered</b>\n\n{exc}\n\n"
                f"Check BACKUP_CHAT_ID and that the bot can post there.",
            )
        return None

    async def _alert(self, key: str, text: str) -> None:
        """Tell admins once per distinct problem, not on every tick."""
        if self._last_alert == key:
            return
        self._last_alert = key
        logger.error(key)
        await self._notifications.notify_admins(text)
