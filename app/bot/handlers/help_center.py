"""The help centre. Every topic body is locale text, editable without code."""

from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot import keyboards
from app.bot.callbacks import HelpCB, Nav
from app.bot.handlers.common import build_context, show
from app.bot.handlers.profile import router
from app.bot.texts import Safe


@router.callback_query(Nav.filter(F.to == "help"))
async def open_help(query: CallbackQuery, state: FSMContext, **data):
    await state.clear()
    context = build_context(data)
    await show(
        query,
        context.text("help.main"),
        keyboards.help_menu(context.texts, context.locale, context.settings.support_url),
    )


@router.callback_query(HelpCB.filter())
async def help_topic(query: CallbackQuery, callback_data: HelpCB, **data):
    """Topic bodies come from the locale file, so policies are editable text."""
    context = build_context(data)
    topic = callback_data.topic
    if topic == "refund":
        text = context.text("help.faq_refund", refund_policy=Safe(context.text("policies.refund")))
    elif topic == "terms":
        text = context.text("help.terms", terms=Safe(context.text("policies.terms")))
    elif topic == "privacy":
        text = context.text("help.privacy", privacy=Safe(context.text("policies.privacy")))
    else:
        text = context.text(f"help.faq_{topic}")

    await show(query, text, keyboards.back_home(context.texts, context.locale, back_to="help"))
