"""Outgoing notifications.

Two audiences: users (who can opt out of everything non-essential) and admins
(who cannot). Sends are best-effort -- a blocked user must never break the
worker that was notifying them.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.logging import get_logger
from app.database.repositories import UserRepository

logger = get_logger(__name__)

#: Telegram tolerates ~30 messages/second; stay comfortably under it.
BROADCAST_RATE = 20


class NotificationService:
    def __init__(
        self,
        bot: Bot,
        session_factory: async_sessionmaker,
        admin_ids: list[int],
    ) -> None:
        self._bot = bot
        self._session_factory = session_factory
        self._admin_ids = admin_ids

    async def notify_user(
        self, user_id: int, text: str, reply_markup=None, essential: bool = False
    ) -> bool:
        """Send to a user, honouring their notification preference.

        ``essential=True`` bypasses the preference; it is for things the user
        is waiting on, such as their SMS code or a settled payment.
        """
        if not essential and not await self._wants_notifications(user_id):
            return False
        return await self._send(user_id, text, reply_markup)

    async def notify_admins(self, text: str) -> None:
        """Best-effort per admin, but a failure here is not routine.

        This is often the fallback of last resort -- e.g. when a payment
        review post fails to reach the channel -- so unlike a blocked
        ordinary user, a failed admin send must be visible at the deployed
        log level, not just at DEBUG.
        """
        for admin_id in self._admin_ids:
            # One admin failing in a way _send() doesn't already catch (a
            # network reset, not just a rejected API call) must not stop the
            # rest of the admins from being notified -- this loop is often
            # the last channel a payment-review failure can reach anyone
            # through. Exception, not BaseException: asyncio.CancelledError
            # must still propagate for a clean shutdown.
            try:
                delivered = await self._send(admin_id, text)
            except Exception:
                logger.warning("notify_admins.failed", admin_id=admin_id, exc_info=True)
                continue
            if not delivered:
                logger.warning("notify_admins.failed", admin_id=admin_id)

    async def broadcast(self, user_ids: list[int], text: str) -> tuple[int, int]:
        """Rate-limited broadcast. Returns ``(delivered, failed)``."""
        delivered = failed = 0
        for index, user_id in enumerate(user_ids, start=1):
            if await self._send(user_id, text):
                delivered += 1
            else:
                failed += 1
            if index % BROADCAST_RATE == 0:
                await asyncio.sleep(1)
        logger.info("broadcast.finished", delivered=delivered, failed=failed)
        return delivered, failed

    async def _wants_notifications(self, user_id: int) -> bool:
        async with self._session_factory() as session:
            user = await UserRepository(session).get(user_id)
            return bool(user and user.notifications_enabled)

    async def _send(self, chat_id: int, text: str, reply_markup=None) -> bool:
        try:
            await self._bot.send_message(chat_id, text, reply_markup=reply_markup)
            return True
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            return await self._send(chat_id, text, reply_markup)
        except TelegramAPIError as exc:
            # Blocked bot, deleted account, chat not found -- all expected.
            logger.debug("notify.failed", chat_id=chat_id, error=str(exc))
            return False
