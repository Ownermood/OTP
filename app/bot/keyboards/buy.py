"""The buy-a-number flow: services, countries, confirmation and the live order."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    ConfirmCB,
    CountryCB,
    FavoriteCB,
    Nav,
    NoopCB,
    OrderCB,
    ServiceCB,
)
from app.bot.keyboards.common import _chunks, _nav_row
from app.bot.texts import Texts
from app.core.constants import GRID_COLUMNS
from app.core.money import format_money
from app.utils.formatting import availability_icon, truncate
from app.utils.pagination import Page


def services(
    texts: Texts,
    locale: str | None,
    page: Page,
    recent: Sequence = (),
    show_search: bool = True,
) -> InlineKeyboardMarkup:
    """Service picker: recently used first, then the paginated catalogue."""
    builder = InlineKeyboardBuilder()

    if recent:
        builder.row(
            InlineKeyboardButton(text=texts.button("recent", locale), callback_data=NoopCB().pack())
        )
        for chunk in _chunks(list(recent), GRID_COLUMNS):
            builder.row(
                *[
                    InlineKeyboardButton(
                        text=truncate(order.service_name, 22),
                        callback_data=ServiceCB(code=order.service_code).pack(),
                    )
                    for order in chunk
                ]
            )

    if show_search:
        builder.row(
            InlineKeyboardButton(
                text=texts.button("search", locale), callback_data=Nav(to="buy_search").pack()
            )
        )

    for chunk in _chunks(list(page.items), GRID_COLUMNS):
        builder.row(
            *[
                InlineKeyboardButton(
                    text=truncate(service.name, 22),
                    callback_data=ServiceCB(code=service.code).pack(),
                )
                for service in chunk
            ]
        )

    nav = _nav_row(texts, page, lambda p: Nav(to="buy", page=p).pack(), locale)
    if len(nav) > 1:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        )
    )
    return builder.as_markup()


def countries(
    texts: Texts,
    locale: str | None,
    page: Page,
    tokens: dict[int, str],
    currency: str,
    back_to: str = "buy",
) -> InlineKeyboardMarkup:
    """Country picker. Each button carries a token, never a price."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("search", locale), callback_data=Nav(to="country_search").pack()
        )
    )
    for chunk in _chunks(list(page.items), GRID_COLUMNS):
        builder.row(
            *[
                InlineKeyboardButton(
                    text=(
                        f"{availability_icon(priced.country.available)} "
                        f"{truncate(priced.country.name, 14)} · "
                        f"{format_money(priced.price, currency)}"
                    ),
                    callback_data=CountryCB(token=tokens[priced.country.id]).pack(),
                )
                for priced in chunk
                if priced.country.id in tokens
            ]
        )

    nav = _nav_row(texts, page, lambda p: Nav(to="countries", page=p).pack(), locale)
    if len(nav) > 1:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale), callback_data=Nav(to=back_to).pack()
        ),
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        ),
    )
    return builder.as_markup()


def purchase_confirm(texts: Texts, locale: str | None, token: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("confirm", locale), callback_data=ConfirmCB(token=token).pack()
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("add_favorite", locale),
            callback_data=FavoriteCB(action="add_token", favorite_id=0).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("cancel", locale), callback_data=Nav(to="buy").pack()
        )
    )
    return builder.as_markup()


def activation(texts: Texts, locale: str | None, order_id: int) -> InlineKeyboardMarkup:
    """Controls on a live activation screen."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("refresh", locale),
            callback_data=OrderCB(action="refresh", order_id=order_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("cancel", locale),
            callback_data=OrderCB(action="cancel", order_id=order_id).pack(),
        ),
        InlineKeyboardButton(
            text=texts.button("details", locale),
            callback_data=OrderCB(action="detail", order_id=order_id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        )
    )
    return builder.as_markup()


def cancel_confirm(texts: Texts, locale: str | None, order_id: int) -> InlineKeyboardMarkup:
    """Destructive action -- always behind an explicit confirmation."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Yes, cancel",
            callback_data=OrderCB(action="cancel_yes", order_id=order_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Keep number",
            callback_data=OrderCB(action="detail", order_id=order_id).pack(),
        )
    )
    return builder.as_markup()
