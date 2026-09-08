"""/start, the main menu and universal navigation."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards
from app.bot.callbacks import Nav, NoopCB
from app.bot.handlers.common import build_context, show
from app.bot.texts import Safe
from app.core.logging import get_logger

router = Router(name="start")
logger = get_logger(__name__)


@router.message(CommandStart())
async def cmd_start(
    message: Message, command: CommandObject, state: FSMContext, **data
) -> None:
    """Entry point. Also where a referral deep link is consumed."""
    await state.clear()
    context = build_context(data)

    if command.args and data.get("is_new_user"):
        inviter_id = context.referrals.parse_start_payload(command.args)
        if inviter_id is not None:
            await context.referrals.link(inviter_id, message.from_user.id)
            await context.session.commit()

    await show(message, *_home_screen(context, data.get("is_new_user", False)))


@router.callback_query(Nav.filter(F.to == "home"))
async def open_home(query: CallbackQuery, state: FSMContext, **data) -> None:
    await state.clear()
    context = build_context(data)
    await show(query, *_home_screen(context, False))


@router.callback_query(NoopCB.filter())
async def noop(query: CallbackQuery) -> None:
    """Page counters and section headers are inert."""
    await query.answer()


def _home_screen(context, is_new: bool):
    """Welcome text for a first visit, balance-led text on every return."""
    keyboard = keyboards.main_menu(context.texts, context.locale, context.smm.enabled)
    if is_new:
        smm_line = Safe(context.text("start.smm_line")) if context.smm.enabled else ""
        text = context.text(
            "start.welcome",
            service_name=context.settings.service_name,
            smm_line=smm_line,
        )
    else:
        text = context.text(
            "start.returning",
            service_name=context.settings.service_name,
            balance=context.money(context.user.balance),
        )
    return text, keyboard
