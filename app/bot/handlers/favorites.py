"""Saved service and country combinations, re-priced on open."""

from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot import keyboards
from app.bot.callbacks import FavoriteCB, Nav
from app.bot.handlers.common import build_context, show, toast
from app.bot.handlers.profile import router
from app.utils.formatting import availability_icon
from app.utils.pagination import paginate


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
