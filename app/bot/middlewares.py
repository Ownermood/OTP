"""Middlewares.

Order matters, and it is set in :mod:`app.bot.setup`:

1. :class:`DatabaseMiddleware` opens one session per update.
2. :class:`UserMiddleware` upserts the user and injects services.
3. :class:`ThrottleMiddleware` rate-limits and drops duplicate callbacks.
4. :class:`MaintenanceMiddleware` blocks non-admins during maintenance.
5. :class:`ErrorMiddleware` turns any exception into a friendly message.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, TelegramObject
from aiogram.types import User as TgUser
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.ack import acknowledge
from app.bot.callbacks import WalletCB
from app.bot.keyboards.style import PRIMARY, button
from app.core.config import Settings
from app.core.exceptions import BotError, InsufficientBalanceError, MaintenanceError
from app.core.logging import get_logger
from app.core.money import format_money
from app.services.admin import AdminService
from app.services.users import UserService
from app.services.wallet import WalletService

logger = get_logger(__name__)


class DatabaseMiddleware(BaseMiddleware):
    """Gives each update its own session, closed when the update is done."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self._session_factory() as session:
            data["session"] = session
            return await handler(event, data)


class UserMiddleware(BaseMiddleware):
    """Upserts the user, blocks banned accounts and injects per-update services."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        session = data["session"]
        wallet = WalletService(session)
        users = UserService(session, wallet, self._settings)
        user, is_new = await users.touch(tg_user.id, tg_user.username, tg_user.full_name)

        if user.is_banned:
            texts = data["texts"]
            await _reply(event, texts.get("errors.banned", user.language))
            return None

        data.update(
            user=user,
            is_new_user=is_new,
            locale=user.language,
            wallet=wallet,
            users=users,
            admin_role=self._settings.role_for(tg_user.id),
        )
        return await handler(event, data)


class ThrottleMiddleware(BaseMiddleware):
    """Rate limiting plus duplicate-callback suppression.

    The duplicate check is what stops a double-tapped button from reaching a
    handler twice; the single-use token in the purchase flow is the second line
    of defence behind it.
    """

    #: Both windows this middleware checks are under two seconds, so any
    #: entry older than this can never affect another decision. Swept
    #: periodically (not on every call) so memory stays bounded across a
    #: long-running process without an unbounded per-user dict, at the cost
    #: of one dict scan a minute rather than per update.
    STALE_AFTER = 60.0
    _SWEEP_INTERVAL = 60.0

    def __init__(self, rate_per_second: float) -> None:
        self._min_interval = 1.0 / max(rate_per_second, 0.1)
        self._last_seen: dict[int, float] = {}
        self._last_callback: dict[int, tuple[str, float]] = {}
        self._last_sweep = 0.0

    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        now = time.monotonic()
        if now - self._last_sweep > self._SWEEP_INTERVAL:
            self._evict_stale(now)
            self._last_sweep = now
        user_id = tg_user.id

        if isinstance(event, CallbackQuery) and event.data:
            previous, at = self._last_callback.get(user_id, ("", 0.0))
            if previous == event.data and now - at < 1.5:
                await event.answer()
                return None
            self._last_callback[user_id] = (event.data, now)

        if now - self._last_seen.get(user_id, 0.0) < self._min_interval:
            texts = data["texts"]
            if isinstance(event, CallbackQuery):
                await event.answer(texts.get("errors.rate_limited"), show_alert=False)
            return None

        self._last_seen[user_id] = now
        return await handler(event, data)

    def _evict_stale(self, now: float) -> None:
        cutoff = now - self.STALE_AFTER
        for user_id in [uid for uid, at in self._last_seen.items() if at < cutoff]:
            del self._last_seen[user_id]
        for user_id in [uid for uid, (_, at) in self._last_callback.items() if at < cutoff]:
            del self._last_callback[user_id]


class MaintenanceMiddleware(BaseMiddleware):
    """Blocks everyone but admins while maintenance mode is on."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if data.get("admin_role") is not None:
            return await handler(event, data)

        admin = AdminService(data["session"], data["wallet"]) if "wallet" in data else None
        if admin is None:
            return await handler(event, data)

        if await admin.is_maintenance(self._settings.maintenance_mode):
            await _reply(event, data["texts"].get("errors.maintenance", data.get("locale")))
            return None
        return await handler(event, data)


class ErrorMiddleware(BaseMiddleware):
    """Last line of defence: a user never sees a traceback.

    Known :class:`BotError`s render their locale message; anything else logs the
    real exception and shows the generic apology.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        try:
            return await handler(event, data)
        except MaintenanceError:
            await _reply(event, data["texts"].get("errors.maintenance", data.get("locale")))
        except BotError as exc:
            await _reply(event, self._render(exc, data), self._keyboard_for(exc, data))
            logger.info(
                "handler.rejected",
                error=type(exc).__name__,
                detail=exc.detail,
                user_id=getattr(data.get("event_from_user"), "id", None),
                **{k: str(v) for k, v in exc.context.items()},
            )
        except TelegramBadRequest as exc:
            # "message is not modified" is normal when a refresh changes nothing.
            if "message is not modified" not in str(exc):
                logger.warning("telegram.bad_request", error=str(exc))
            if isinstance(event, CallbackQuery):
                # The recovery must not raise the very error it is recovering
                # from: the query that expired mid-handler is still expired.
                await acknowledge(event)
        except Exception:
            logger.error(
                "handler.crashed",
                user_id=getattr(data.get("event_from_user"), "id", None),
                exc_info=True,
            )
            await _reply(event, data["texts"].get("errors.generic", data.get("locale")))
        return None

    def _render(self, exc: BotError, data: dict[str, Any]) -> str:
        texts = data["texts"]
        locale = data.get("locale")
        values: dict[str, Any] = {}
        # Money-valued context is formatted here so locale files stay unit-agnostic.
        for key in ("required", "available", "minimum", "maximum"):
            if key in exc.context:
                values[key] = format_money(
                    int(exc.context[key]), self._settings.currency_symbol
                )
        return texts.get(exc.message_key, locale, **values)

    def _keyboard_for(self, exc: BotError, data: dict[str, Any]) -> InlineKeyboardMarkup | None:
        """A dead-end error screen strands the user; some errors get a way out."""
        if isinstance(exc, InsufficientBalanceError):
            texts = data["texts"]
            locale = data.get("locale")
            builder = InlineKeyboardBuilder()
            builder.row(
                button(
                    texts.button("deposit", locale),
                    callback_data=WalletCB(action="deposit").pack(),
                    style=PRIMARY,
                )
            )
            return builder.as_markup()
        return None


async def _reply(
    event: TelegramObject, text: str, keyboard: InlineKeyboardMarkup | None = None
) -> None:
    """Answer whichever event type we have, swallowing delivery failures."""
    try:
        if isinstance(event, CallbackQuery):
            await event.answer()
            if event.message:
                await event.message.answer(text, reply_markup=keyboard)
        elif isinstance(event, Message):
            await event.answer(text, reply_markup=keyboard)
    except TelegramBadRequest as exc:
        logger.debug("reply.failed", error=str(exc))
