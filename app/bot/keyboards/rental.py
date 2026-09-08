"""The rent-a-number flow: country, duration, then services at real prices."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    Nav,
    RentCB,
)
from app.bot.keyboards.common import _chunks, _nav_row
from app.bot.texts import Texts
from app.core.constants import GRID_COLUMNS, RENTAL_PRESET_HOURS
from app.core.money import format_money
from app.utils.formatting import availability_icon, truncate
from app.utils.pagination import Page


def rental_countries(
    texts: Texts, locale: str | None, page: Page
) -> InlineKeyboardMarkup:
    """Country picker for rentals. Prices are not known until a duration is set."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("search", locale),
            callback_data=RentCB(action="search").pack(),
        )
    )
    for chunk in _chunks(list(page.items), GRID_COLUMNS):
        builder.row(
            *[
                InlineKeyboardButton(
                    text=truncate(country.name, 20),
                    callback_data=RentCB(action="country", value=str(country.id)).pack(),
                )
                for country in chunk
            ]
        )
    nav = _nav_row(texts, page, lambda p: RentCB(action="list", page=p).pack(), locale)
    if len(nav) > 1:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        )
    )
    return builder.as_markup()


def rental_durations(
    texts: Texts, locale: str | None, country_id: int, minimum: int, maximum: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    presets = [h for h in RENTAL_PRESET_HOURS if minimum <= h <= maximum]
    for chunk in _chunks(presets, 3):
        builder.row(
            *[
                InlineKeyboardButton(
                    text=(f"{h}h" if h < 24 else f"{h // 24}d"),
                    callback_data=RentCB(
                        action="hours", value=f"{country_id}_{h}"
                    ).pack(),
                )
                for h in chunk
            ]
        )
    builder.row(
        InlineKeyboardButton(
            text="⚙️ Custom",
            callback_data=RentCB(action="custom", value=str(country_id)).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale), callback_data=Nav(to="rent").pack()
        ),
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        ),
    )
    return builder.as_markup()


def rental_services(
    texts: Texts,
    locale: str | None,
    page: Page,
    tokens: dict[str, str],
    country_id: int,
    hours: int,
    currency: str,
) -> InlineKeyboardMarkup:
    """Rentable services at their real price for the chosen duration."""
    builder = InlineKeyboardBuilder()
    for priced in page.items:
        token = tokens.get(priced.offer.code)
        if token is None:
            continue
        builder.row(
            InlineKeyboardButton(
                text=(
                    f"{availability_icon(priced.offer.available)} "
                    f"{truncate(priced.offer.name, 22)} · "
                    f"{format_money(priced.price, currency)}"
                ),
                callback_data=RentCB(action="quote", value=token).pack(),
            )
        )
    nav = _nav_row(
        texts,
        page,
        lambda p: RentCB(action="hours", value=f"{country_id}_{hours}", page=p).pack(),
        locale,
    )
    if len(nav) > 1:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale),
            callback_data=RentCB(action="country", value=str(country_id)).pack(),
        ),
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        ),
    )
    return builder.as_markup()
