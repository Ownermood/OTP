"""Profile and user settings.

The router lives here; favourites, referrals and the help centre register on
it from their own modules.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot import keyboards
from app.bot.callbacks import Nav, SettingsCB
from app.bot.handlers.common import build_context, show, toast
from app.core.logging import get_logger

router = Router(name="profile")
logger = get_logger(__name__)

@router.callback_query(Nav.filter(F.to == "profile"))
async def open_profile(query: CallbackQuery, state: FSMContext, **data):
    await state.clear()
    context = build_context(data)
    stats = await context.users.stats(query.from_user.id)
    await show(
        query,
        context.text(
            "profile.main",
            name=context.user.full_name or context.user.username or "there",
            user_id=context.user.id,
            balance=context.money(context.user.balance),
            activations=stats.activations,
            rentals=stats.rentals,
            smm_orders=stats.smm_orders,
            total_spent=context.money(stats.total_spent),
            referral_earned=context.money(stats.referral_earned),
        ),
        keyboards.profile(context.texts, context.locale),
    )


# -- favourites -------------------------------------------------------------


@router.callback_query(Nav.filter(F.to == "settings"))
async def open_settings(query: CallbackQuery, **data):
    context = build_context(data)
    await _render_settings(query, context)


@router.callback_query(SettingsCB.filter(F.action == "notifications"))
async def toggle_notifications(query: CallbackQuery, **data):
    context = build_context(data)
    enabled = not context.user.notifications_enabled
    await context.users.set_notifications(query.from_user.id, enabled)
    context.user.notifications_enabled = enabled
    await toast(
        query, context.text("settings.notifications_on" if enabled else "settings.notifications_off")
    )
    await _render_settings(query, context)


@router.callback_query(SettingsCB.filter(F.action == "language"))
async def set_language(query: CallbackQuery, callback_data: SettingsCB, **data):
    context = build_context(data)
    if callback_data.value not in context.texts.locales:
        await toast(query, context.text("errors.invalid_input"), alert=True)
        return
    await context.users.set_language(query.from_user.id, callback_data.value)
    context.locale = callback_data.value
    context.user.language = callback_data.value
    await _render_settings(query, context)


# -- help -------------------------------------------------------------------


async def _render_settings(event, context) -> None:
    await show(
        event,
        context.text(
            "settings.main",
            notifications="ON" if context.user.notifications_enabled else "OFF",
            language=context.locale.upper(),
        ),
        keyboards.settings_menu(
            context.texts,
            context.locale,
            context.user.notifications_enabled,
            context.texts.locales,
        ),
    )
