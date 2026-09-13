"""Outgoing notifications.

The bug this file guards against: a failed *admin* notification was logged at
DEBUG level, the same as a routine blocked-user send. In production
(LOG_LEVEL=INFO) that made the "admins must hear about it directly" fallback
-- used when a payment review post fails to reach the channel -- completely
invisible. The payment itself was never lost (it's saved to the database
either way), but nobody could tell whether the fallback DM actually landed.
"""

from app.services import notifications as notifications_module
from app.services.notifications import NotificationService


class _FailingBot:
    """A bot whose every send is rejected by Telegram, like a channel the bot
    isn't (yet) an admin of, or a user who has blocked it."""

    async def send_message(self, chat_id, text, reply_markup=None):
        from aiogram.exceptions import TelegramAPIError

        raise TelegramAPIError(method=None, message="Bad Request: chat not found")


class _WorkingBot:
    async def send_message(self, chat_id, text, reply_markup=None):
        return None


async def test_a_failed_admin_notification_is_logged_visibly(monkeypatch, session_factory):
    """The admin fallback exists specifically so admins hear about failures --
    its own failure must not be invisible at the deployed log level."""
    warnings = []
    monkeypatch.setattr(
        notifications_module.logger, "warning", lambda *a, **k: warnings.append((a, k))
    )

    service = NotificationService(_FailingBot(), session_factory, admin_ids=[555001])
    await service.notify_admins("a payment needs review")

    assert warnings, "a failed admin notification must be logged at a visible level"


async def test_a_successful_admin_notification_logs_no_warning(monkeypatch, session_factory):
    warnings = []
    monkeypatch.setattr(
        notifications_module.logger, "warning", lambda *a, **k: warnings.append((a, k))
    )

    service = NotificationService(_WorkingBot(), session_factory, admin_ids=[555001])
    await service.notify_admins("a payment needs review")

    assert warnings == []


class _PartiallyBrokenBot:
    """The first admin's send raises something _send() itself doesn't catch
    (a plain RuntimeError, not a TelegramAPIError) -- the rest must still be
    attempted rather than the whole loop dying there."""

    def __init__(self) -> None:
        self.sent_to: list[int] = []

    async def send_message(self, chat_id, text, reply_markup=None):
        if chat_id == 111:
            raise RuntimeError("unexpected network reset")
        self.sent_to.append(chat_id)


async def test_one_admins_unexpected_failure_does_not_stop_the_rest(monkeypatch, session_factory):
    warnings = []
    monkeypatch.setattr(
        notifications_module.logger, "warning", lambda *a, **k: warnings.append((a, k))
    )
    bot = _PartiallyBrokenBot()
    service = NotificationService(bot, session_factory, admin_ids=[111, 222])

    await service.notify_admins("a payment needs review")

    assert bot.sent_to == [222]  # the second admin was still reached
    assert any(kwargs.get("admin_id") == 111 for _, kwargs in warnings)


async def test_a_blocked_routine_user_does_not_warn(monkeypatch, session_factory):
    """Routine user sends are best-effort; a blocked bot is expected and must
    stay quiet, unlike the admin-facing fallback above."""
    warnings = []
    monkeypatch.setattr(
        notifications_module.logger, "warning", lambda *a, **k: warnings.append((a, k))
    )

    service = NotificationService(_FailingBot(), session_factory, admin_ids=[555001])
    await service.notify_user(999, "your order is ready", essential=True)

    assert warnings == []
