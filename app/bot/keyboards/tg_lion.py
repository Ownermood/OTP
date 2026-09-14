"""TG-Lion Telegram numbers: country list, purchase confirm, and the live
number/OTP screens (purchased -> waiting -> received)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import Nav, OrderCB, TgLionCB
from app.bot.keyboards.common import _nav_row
from app.bot.keyboards.style import DANGER, PRIMARY, SUCCESS, button
from app.bot.texts import Texts
from app.core.money import format_money
from app.utils.pagination import Page


def tg_lion_countries(
    texts: Texts, locale: str | None, page: Page, currency: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("search", locale),
            icon_custom_emoji_id=texts.icon("search"),
            callback_data=Nav(to="telegram_search").pack(),
        )
    )
    for country in page.items:
        builder.row(
            InlineKeyboardButton(
                text=f"{country.name} · {format_money(country.cost, currency)}",
                callback_data=TgLionCB(action="country", country=country.code).pack(),
            )
        )
    nav = _nav_row(texts, page, lambda p: TgLionCB(action="page", page=p).pack(), locale)
    if len(nav) > 1:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale),
            icon_custom_emoji_id=texts.icon("home"),
            callback_data=Nav(to="home").pack(),
        )
    )
    return builder.as_markup()


def tg_lion_confirm(texts: Texts, locale: str | None, country_code: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("buy_now", locale),
            icon_custom_emoji_id=texts.icon("buy"),
            callback_data=TgLionCB(action="buy", country=country_code).pack(),
            style=SUCCESS,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale),
            icon_custom_emoji_id=texts.icon("back"),
            callback_data=Nav(to="telegram").pack(),
        )
    )
    return builder.as_markup()


def tg_number_purchased(
    texts: Texts, locale: str | None, order_id: int, phone: str
) -> InlineKeyboardMarkup:
    """Right after buying: number on screen, one tap to ask for the code."""
    builder = InlineKeyboardBuilder()
    builder.row(button(texts.button("copy_number", locale), copy=phone))
    builder.row(
        InlineKeyboardButton(
            text=texts.button("get_otp", locale),
            icon_custom_emoji_id=texts.icon("otp"),
            callback_data=OrderCB(action="tg_refresh", order_id=order_id).pack(),
            style=PRIMARY,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("cancel", locale),
            icon_custom_emoji_id=texts.icon("cancel"),
            callback_data=OrderCB(action="tg_cancel", order_id=order_id).pack(),
            style=DANGER,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale),
            icon_custom_emoji_id=texts.icon("home"),
            callback_data=Nav(to="home").pack(),
        )
    )
    return builder.as_markup()


def tg_number_waiting(texts: Texts, locale: str | None, order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("refresh", locale),
            icon_custom_emoji_id=texts.icon("refresh"),
            callback_data=OrderCB(action="tg_refresh", order_id=order_id).pack(),
        ),
        InlineKeyboardButton(
            text=texts.button("cancel", locale),
            icon_custom_emoji_id=texts.icon("cancel"),
            callback_data=OrderCB(action="tg_cancel", order_id=order_id).pack(),
            style=DANGER,
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale),
            icon_custom_emoji_id=texts.icon("home"),
            callback_data=Nav(to="home").pack(),
        )
    )
    return builder.as_markup()


def tg_number_received(
    texts: Texts, locale: str | None, phone: str, code: str, country_code: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        button(texts.button("copy_number", locale), copy=phone),
        button(texts.button("copy_code", locale), copy=code),
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("buy_again", locale),
            icon_custom_emoji_id=texts.icon("buy"),
            callback_data=TgLionCB(action="buy", country=country_code).pack(),
            style=SUCCESS,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale),
            icon_custom_emoji_id=texts.icon("back"),
            callback_data=Nav(to="telegram").pack(),
        ),
        InlineKeyboardButton(
            text=texts.button("home", locale),
            icon_custom_emoji_id=texts.icon("home"),
            callback_data=Nav(to="home").pack(),
        ),
    )
    return builder.as_markup()
