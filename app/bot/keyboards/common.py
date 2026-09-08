"""Shared building blocks: the main menu, back/home rows and pagination."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    Nav,
    NoopCB,
)
from app.bot.keyboards.style import DANGER, PRIMARY, SUCCESS
from app.bot.texts import Texts
from app.utils.pagination import Page


def _nav_row(
    texts: Texts,
    page: Page,
    callback_factory,
    locale: str | None = None,
) -> list[InlineKeyboardButton]:
    """The standard ⬅️ 1/4 ➡️ row shared by every paginated list."""
    row: list[InlineKeyboardButton] = []
    if page.has_previous:
        row.append(
            InlineKeyboardButton(
                text=texts.button("previous", locale),
                callback_data=callback_factory(page.page - 1),
            )
        )
    row.append(InlineKeyboardButton(text=page.label, callback_data=NoopCB().pack()))
    if page.has_next:
        row.append(
            InlineKeyboardButton(
                text=texts.button("next", locale), callback_data=callback_factory(page.page + 1)
            )
        )
    return row


def _chunks(items: list, size: int) -> list[list]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def main_menu(texts: Texts, locale: str | None, smm_enabled: bool) -> InlineKeyboardMarkup:
    """The home screen. One primary action, then pairs."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("buy", locale), icon_custom_emoji_id=texts.icon("buy"), callback_data=Nav(to="buy").pack(), style=SUCCESS
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("orders", locale), icon_custom_emoji_id=texts.icon("orders"), callback_data=Nav(to="orders").pack(), style=PRIMARY
        ),
        InlineKeyboardButton(
            text=texts.button("favorites", locale), icon_custom_emoji_id=texts.icon("favorites"), callback_data=Nav(to="favorites").pack(), style=PRIMARY
        ),
    )
    if smm_enabled:
        builder.row(
            InlineKeyboardButton(
                text=texts.button("smm", locale), icon_custom_emoji_id=texts.icon("smm"), callback_data=Nav(to="smm").pack(), style=PRIMARY
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("profile", locale), icon_custom_emoji_id=texts.icon("profile"), callback_data=Nav(to="profile").pack(), style=PRIMARY
        ),
        InlineKeyboardButton(
            text=texts.button("wallet", locale), icon_custom_emoji_id=texts.icon("wallet"), callback_data=Nav(to="wallet").pack(), style=DANGER
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("referral", locale), icon_custom_emoji_id=texts.icon("referral"), callback_data=Nav(to="referral").pack(), style=PRIMARY
        ),
        InlineKeyboardButton(
            text=texts.button("help", locale), icon_custom_emoji_id=texts.icon("help"), callback_data=Nav(to="help").pack()
        ),
    )
    return builder.as_markup()


def back_home(texts: Texts, locale: str | None, back_to: str = "home") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if back_to != "home":
        builder.row(
            InlineKeyboardButton(
                text=texts.button("back", locale), callback_data=Nav(to=back_to).pack()
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        )
    )
    return builder.as_markup()


def confirm_or_cancel(
    texts: Texts, locale: str | None, confirm_callback: str, cancel_to: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=texts.button("confirm", locale), callback_data=confirm_callback, style=SUCCESS)
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("cancel", locale), callback_data=Nav(to=cancel_to).pack()
        )
    )
    return builder.as_markup()
