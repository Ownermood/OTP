"""Answering a callback query without letting Telegram's clock crash a handler."""

from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from app.core.logging import get_logger

logger = get_logger(__name__)

#: Telegram's wording when the query has already expired on its side.
_EXPIRED = ("query is too old", "query ID is invalid")


async def acknowledge(
    event: CallbackQuery, text: str | None = None, alert: bool = False
) -> None:
    """Answer a callback, tolerating one Telegram has already given up on.

    A query expires while the handler is still working, and answering an
    expired one raises. That turned a slow screen into a crash -- and the error
    handler, whose own recovery is to answer the callback, raised again on top
    of it. The user stopped waiting either way; the screen still renders.
    """
    try:
        await event.answer(text, show_alert=alert)
    except TelegramBadRequest as exc:
        if not any(phrase in str(exc) for phrase in _EXPIRED):
            raise
        logger.info("callback.expired", data=event.data)
