"""Order history, order detail and favourites."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    CountryCB,
    FavoriteCB,
    Nav,
    OrderCB,
    OrdersListCB,
    WalletCB,
)
from app.bot.keyboards.common import _nav_row
from app.bot.keyboards.style import DANGER, SUCCESS
from app.bot.texts import Texts
from app.core.money import format_money
from app.utils.formatting import order_icon, truncate
from app.utils.pagination import Page


def orders_root(texts: Texts, locale: str | None, smm_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📱 SMS Activations", callback_data=OrdersListCB(kind="activation").pack()
        )
    )
    if smm_enabled:
        builder.row(
            InlineKeyboardButton(text="📈 SMM", callback_data=OrdersListCB(kind="smm").pack())
        )
    builder.row(
        InlineKeyboardButton(
            text="💳 Payments", callback_data=WalletCB(action="history").pack()
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        )
    )
    return builder.as_markup()


def orders_list(
    texts: Texts, locale: str | None, page: Page, kind: str, currency: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in page.items:
        location = f" · {order.country_name}" if order.country_name else ""
        builder.row(
            InlineKeyboardButton(
                text=(
                    f"{order_icon(order.status)} #{order.id} "
                    f"{truncate(order.service_name, 16)}{location} · "
                    f"{format_money(order.price, currency)}"
                ),
                callback_data=OrderCB(action="detail", order_id=order.id).pack(),
            )
        )
    nav = _nav_row(texts, page, lambda p: OrdersListCB(kind=kind, page=p).pack(), locale)
    if len(nav) > 1:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale), callback_data=Nav(to="orders").pack()
        ),
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        ),
    )
    return builder.as_markup()


def order_detail(
    texts: Texts, locale: str | None, order, back_kind: str
) -> InlineKeyboardMarkup:
    """Controls for one order.

    Cancel shows only while an SMS order is still open. SMM orders are already
    being delivered by the panel, so there is nothing to cancel and refunding
    one would be a straight loss.
    """
    from app.core.constants import OrderKind, OrderStatus

    builder = InlineKeyboardBuilder()
    if not OrderStatus(order.status).is_final:
        controls = [
            InlineKeyboardButton(
                text=texts.button("refresh", locale),
                callback_data=OrderCB(action="refresh", order_id=order.id).pack(),
            )
        ]
        if OrderKind(order.kind) is not OrderKind.SMM:
            controls.append(
                InlineKeyboardButton(
                    text=texts.button("cancel", locale),
                    callback_data=OrderCB(action="cancel", order_id=order.id).pack(), style=DANGER,
                )
            )
        builder.row(*controls)
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale),
            callback_data=OrdersListCB(kind=back_kind).pack(),
        ),
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        ),
    )
    return builder.as_markup()


def favorites_list(texts: Texts, locale: str | None, page: Page) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for favorite in page.items:
        builder.row(
            InlineKeyboardButton(
                text=f"⭐ {favorite.country_name} — {truncate(favorite.service_name, 18)}",
                callback_data=FavoriteCB(action="open", favorite_id=favorite.id).pack(),
            )
        )
    nav = _nav_row(texts, page, lambda p: Nav(to="favorites", page=p).pack(), locale)
    if len(nav) > 1:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        )
    )
    return builder.as_markup()


def favorite_detail(
    texts: Texts, locale: str | None, favorite_id: int, token: str | None
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if token:
        builder.row(
            InlineKeyboardButton(
                text=texts.button("buy_now", locale), callback_data=CountryCB(token=token).pack(), style=SUCCESS
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("remove", locale),
            callback_data=FavoriteCB(action="remove", favorite_id=favorite_id).pack(), style=DANGER,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale), callback_data=Nav(to="favorites").pack()
        )
    )
    return builder.as_markup()
