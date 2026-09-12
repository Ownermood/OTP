"""The referral programme screen and its history."""

from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot import keyboards
from app.bot.callbacks import Nav
from app.bot.handlers.common import build_context, show
from app.bot.handlers.profile import router


@router.callback_query(Nav.filter(F.to == "referral"))
async def open_referral(query: CallbackQuery, state: FSMContext, **data):
    await state.clear()
    context = build_context(data)
    bot_user = await query.bot.me()
    link = context.referrals.link_for(bot_user.username, query.from_user.id)
    stats = await context.referrals.stats(query.from_user.id)

    await show(
        query,
        context.text(
            "referral.main",
            invited=stats.invited,
            earned=context.money(stats.earned),
            percent=stats.percent,
            link=link,
        ),
        keyboards.referral(
            context.texts, context.locale, f"https://t.me/share/url?url={link}", link
        ),
    )


@router.callback_query(Nav.filter(F.to == "referral_history"))
async def referral_history(query: CallbackQuery, **data):
    context = build_context(data)
    referrals = await context.referrals.history(query.from_user.id)
    lines = [
        f"👤 <code>{ref.invited_id}</code> — {context.money(ref.earned)}" for ref in referrals[:20]
    ]
    body = "\n".join(lines) if lines else context.text("common.empty")
    await show(
        query,
        context.text("referral.history", count=len(referrals)) + "\n\n" + body,
        keyboards.back_home(context.texts, context.locale, back_to="referral"),
    )


# -- settings ---------------------------------------------------------------
