"""The SMM panel: platforms, services and order tracking."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    Nav,
    SmmCB,
)
from app.bot.keyboards.common import _nav_row
from app.bot.keyboards.style import PRIMARY
from app.bot.texts import Texts
from app.core.money import format_money
from app.utils.formatting import truncate
from app.utils.pagination import Page


def smm_categories(
    texts: Texts, locale: str | None, categories: Sequence[tuple]
) -> InlineKeyboardMarkup:
    icons = {
        "instagram": "🟣 Instagram",
        "telegram": "🔵 Telegram",
        "youtube": "🔴 YouTube",
        "tiktok": "⚫️ TikTok",
        "facebook": "🔷 Facebook",
        "twitter": "⚪️ X / Twitter",
        "other": "🌐 Other Services",
    }
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("show_all", locale),
            callback_data=SmmCB(action="show_all").pack(), style=PRIMARY,
        ),
        InlineKeyboardButton(
            text=texts.button("search", locale), callback_data=SmmCB(action="search").pack(), style=PRIMARY
        ),
    )
    for category, count in categories:
        builder.row(
            InlineKeyboardButton(
                text=f"{icons.get(category.value, category.value.title())} ({count})",
                callback_data=SmmCB(action="category", value=category.value).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        )
    )
    return builder.as_markup()


def smm_services(
    texts: Texts, locale: str | None, page: Page, category: str | None, currency: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for service in page.items:
        builder.row(
            InlineKeyboardButton(
                text=(
                    f"{truncate(service.name, 30)} · "
                    f"{format_money(service.rate_per_1000, currency)}/1k"
                ),
                callback_data=SmmCB(action="service", value=service.service_id).pack(),
            )
        )
    if category is not None:
        nav = _nav_row(
            texts, page, lambda p: SmmCB(action="category", value=category, page=p).pack(), locale
        )
        if len(nav) > 1:
            builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale), callback_data=Nav(to="smm").pack()
        ),
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        ),
    )
    return builder.as_markup()


def smm_order(texts: Texts, locale: str | None, order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔄 Track Status", callback_data=SmmCB(action="track", value=str(order_id)).pack(), style=PRIMARY
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        )
    )
    return builder.as_markup()
