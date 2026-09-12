"""Startup wiring that isn't covered by the flow harness."""

from unittest.mock import AsyncMock

from aiogram.types import BotCommand

from app.bot.setup import COMMAND_MENU, register_commands
from app.bot.texts import Texts
from app.core.config import ROOT_DIR


async def test_register_commands_populates_the_native_command_menu():
    """The Telegram '/' menu should list every top-level command, with text."""
    texts = Texts(ROOT_DIR / "locales", "en")
    bot = AsyncMock()

    await register_commands(bot, texts, "en")

    bot.set_my_commands.assert_awaited_once()
    (sent,), _ = bot.set_my_commands.call_args
    assert [c.command for c in sent] == COMMAND_MENU
    assert all(isinstance(c, BotCommand) and c.description for c in sent)
