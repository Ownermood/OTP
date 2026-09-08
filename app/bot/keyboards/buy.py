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
    QuoteCB,
)
from app.bot.keyboards.common import _chunks, _nav_row
from app.bot.keyboards.style import DANGER, PRIMARY, SUCCESS
from app.bot.texts import Texts
from app.core.constants import GRID_COLUMNS
from app.core.countries import dial_code, iso_code
from app.core.money import format_money
from app.utils.formatting import availability_icon, truncate
from app.utils.pagination import Page


def country_grid(
    texts: Texts,
    locale: str | None,
    page: Page,
    currency: str,
    recent: Sequence = (),
    recent_tokens: dict[str, str] | None = None,
) -> InlineKeyboardMarkup:
    """The opening screen: which country do you want a number from.

    Countries come first because that is the question a buyer actually has,
    and because providers price *per country* -- a service list without one
    chosen is 2000 opaque codes with no prices against them.
    """
    builder = InlineKeyboardBuilder()
    tokens = recent_tokens or {}
    if recent and tokens:
        builder.row(
            InlineKeyboardButton(text=texts.button("recent", locale), callback_data=NoopCB().pack())
        )
        for chunk in _chunks([o for o in recent if _recent_key(o) in tokens], GRID_COLUMNS):
            builder.row(
                *[
                    InlineKeyboardButton(
                        text=truncate(f"{order.service_name} · {order.country_name}", 22),
                        callback_data=QuoteCB(token=tokens[_recent_key(order)]).pack(),
                    )
                    for order in chunk
                ]
            )

    builder.row(
        InlineKeyboardButton(
            text=texts.button("show_all", locale),
            callback_data=Nav(to="countries_all").pack(), style=PRIMARY,
        ),
        InlineKeyboardButton(
            text=texts.button("search", locale),
            callback_data=Nav(to="country_search").pack(), style=PRIMARY,
        ),
    )
    for chunk in _chunks(list(page.items), GRID_COLUMNS):
        builder.row(
            *[
                InlineKeyboardButton(
                    text=country_label(priced, currency),
                    callback_data=CountryCB(id=priced.country.id).pack(),
                )
                for priced in chunk
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


def _recent_key(order) -> str:
    """A recent purchase is identified by the pair it repeats."""
    return f"{order.service_code}@{order.country_id}"


def country_label(priced, currency: str) -> str:
    """``🇮🇳 IN +91 · ₹13`` -- flag, short code, dial code, cheapest price.

    The ISO code rather than the name keeps two buttons per row readable; a
    country we have no code for falls back to its (truncated) name.
    """
    name = priced.country.name
    short = iso_code(name) or truncate(name, 10)
    dial = dial_code(name)
    head = " ".join(part for part in (priced.country.flag, short, dial) if part)
    return f"{head} · {format_money(priced.price, currency)}"


def country_services(
    texts: Texts,
    locale: str | None,
    page: Page,
    tokens: dict[str, str],
    currency: str,
) -> InlineKeyboardMarkup:
    """Service picker *within a country*. Each button carries a token, never a price."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("show_all", locale),
            callback_data=Nav(to="services_all").pack(), style=PRIMARY,
        ),
        InlineKeyboardButton(
            text=texts.button("search", locale),
            callback_data=Nav(to="buy_search").pack(), style=PRIMARY,
        ),
    )
    for chunk in _chunks(list(page.items), GRID_COLUMNS):
        builder.row(
            *[
                InlineKeyboardButton(
                    text=(
                        f"{availability_icon(priced.offer.available)} "
                        f"{truncate(priced.offer.service.name, 12)} · "
                        f"{format_money(priced.price, currency)}"
                    ),
                    callback_data=QuoteCB(token=tokens[priced.offer.service.code]).pack(),
                )
                for priced in chunk
                if priced.offer.service.code in tokens
            ]
        )

    nav = _nav_row(texts, page, lambda p: Nav(to="country", page=p).pack(), locale)
    if len(nav) > 1:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale), callback_data=Nav(to="buy").pack()
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
            text=texts.button("confirm", locale), callback_data=ConfirmCB(token=token).pack(), style=SUCCESS
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
            text=texts.button("cancel", locale), callback_data=Nav(to="buy").pack(), style=DANGER
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
            callback_data=OrderCB(action="cancel", order_id=order_id).pack(), style=DANGER,
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
            callback_data=OrderCB(action="cancel_yes", order_id=order_id).pack(), style=DANGER,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Keep number",
            callback_data=OrderCB(action="detail", order_id=order_id).pack(), style=SUCCESS,
        )
    )
    return builder.as_markup()
