"""Profile, favourites, referrals, settings and the help centre."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot import keyboards
from app.bot.callbacks import FavoriteCB, HelpCB, Nav, SettingsCB
from app.bot.handlers.common import build_context, show, toast
from app.bot.texts import Safe
from app.core.logging import get_logger
from app.utils.formatting import availability_icon
from app.utils.pagination import paginate

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


@router.callback_query(Nav.filter(F.to == "favorites"))
async def open_favorites(query: CallbackQuery, callback_data: Nav, state: FSMContext, **data):
    await state.clear()
    context = build_context(data)
    favorites = await context.users.list_favorites(query.from_user.id)

    if not favorites:
        await show(
            query,
            context.text("favorites.empty"),
            keyboards.back_home(context.texts, context.locale),
        )
        return

    await show(
        query,
        context.text("favorites.list"),
        keyboards.favorites_list(
            context.texts, context.locale, paginate(favorites, callback_data.page, per_page=8)
        ),
    )


@router.callback_query(FavoriteCB.filter(F.action == "open"))
async def open_favorite(query: CallbackQuery, callback_data: FavoriteCB, **data):
    """Show a saved combination with its *current* price, re-quoted live."""
    context = build_context(data)
    favorite = await context.users.get_favorite(callback_data.favorite_id, query.from_user.id)
    if favorite is None:
        await toast(query, context.text("errors.order_not_found"), alert=True)
        return

    priced = await context.catalog.find_country(favorite.service_code, favorite.country_id)
    token = None
    if priced is not None:
        token = context.tokens.issue(
            query.from_user.id,
            service_code=favorite.service_code,
            service_name=favorite.service_name,
            country_id=favorite.country_id,
            country_name=favorite.country_name,
            price=priced.price,
        )

    available = priced.country.available if priced else None
    await show(
        query,
        context.text(
            "favorites.detail",
            country=favorite.country_name,
            service=favorite.service_name,
            price=context.money(priced.price) if priced else "—",
            availability_icon=availability_icon(available),
            availability=("Available" if priced else "Unavailable"),
        ),
        keyboards.favorite_detail(context.texts, context.locale, favorite.id, token),
    )


@router.callback_query(FavoriteCB.filter(F.action == "remove"))
async def remove_favorite(query: CallbackQuery, callback_data: FavoriteCB, state: FSMContext, **data):
    context = build_context(data)
    await context.users.remove_favorite(callback_data.favorite_id, query.from_user.id)
    await toast(query, context.text("favorites.removed"))
    await open_favorites(query, Nav(to="favorites"), state, **data)


# -- referrals --------------------------------------------------------------


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
        keyboards.referral(context.texts, context.locale, f"https://t.me/share/url?url={link}"),
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
