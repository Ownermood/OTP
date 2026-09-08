"""Profile, wallet, payments, referrals, settings and the help centre."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    HelpCB,
    Nav,
    PaymentCB,
    SettingsCB,
    WalletCB,
)
from app.bot.keyboards.common import _chunks, _nav_row
from app.bot.texts import Texts
from app.utils.pagination import Page


def profile(texts: Texts, locale: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("deposit", locale), callback_data=WalletCB(action="deposit").pack()
        ),
        InlineKeyboardButton(
            text=texts.button("orders", locale), callback_data=Nav(to="orders").pack()
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("referral", locale), callback_data=Nav(to="referral").pack()
        ),
        InlineKeyboardButton(
            text=texts.button("favorites", locale), callback_data=Nav(to="favorites").pack()
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("promo", locale), callback_data=WalletCB(action="promo").pack()
        ),
        InlineKeyboardButton(
            text=texts.button("settings", locale), callback_data=Nav(to="settings").pack()
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        )
    )
    return builder.as_markup()


def wallet(texts: Texts, locale: str | None, transfer_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("deposit", locale), callback_data=WalletCB(action="deposit").pack()
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("history", locale), callback_data=WalletCB(action="history").pack()
        ),
        InlineKeyboardButton(
            text=texts.button("promo", locale), callback_data=WalletCB(action="promo").pack()
        ),
    )
    if transfer_enabled:
        builder.row(
            InlineKeyboardButton(
                text=texts.button("transfer", locale),
                callback_data=WalletCB(action="transfer").pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        )
    )
    return builder.as_markup()


def payment_methods(
    texts: Texts, locale: str | None, providers: dict[str, str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for name, label in providers.items():
        builder.row(
            InlineKeyboardButton(
                text=label, callback_data=PaymentCB(action="method", provider=name).pack()
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale), callback_data=Nav(to="wallet").pack()
        )
    )
    return builder.as_markup()


def invoice(
    texts: Texts, locale: str | None, payment_id: int, pay_url: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if pay_url:
        builder.row(InlineKeyboardButton(text=texts.button("pay", locale), url=pay_url))
    builder.row(
        InlineKeyboardButton(
            text=texts.button("check_payment", locale),
            callback_data=PaymentCB(action="check", payment_id=payment_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("cancel", locale),
            callback_data=PaymentCB(action="cancel", payment_id=payment_id).pack(),
        )
    )
    return builder.as_markup()


def transactions_filters(texts: Texts, locale: str | None, page: Page) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    filters = [
        ("all", "All"),
        ("deposit", "➕ Deposits"),
        ("purchase", "🛍 Purchases"),
        ("refund", "↩️ Refunds"),
        ("referral", "🎁 Referral"),
    ]
    for chunk in _chunks(filters, 3):
        builder.row(
            *[
                InlineKeyboardButton(
                    text=label, callback_data=WalletCB(action=f"history_{key}").pack()
                )
                for key, label in chunk
            ]
        )
    nav = _nav_row(texts, page, lambda p: WalletCB(action="history", page=p).pack(), locale)
    if len(nav) > 1:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale), callback_data=Nav(to="wallet").pack()
        )
    )
    return builder.as_markup()


def referral(texts: Texts, locale: str | None, share_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=texts.button("share", locale), url=share_url))
    builder.row(
        InlineKeyboardButton(
            text=texts.button("history", locale), callback_data=Nav(to="referral_history").pack()
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        )
    )
    return builder.as_markup()


def settings_menu(
    texts: Texts, locale: str | None, notifications: bool, locales: Sequence[str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=("🔔 Notifications: ON" if notifications else "🔕 Notifications: OFF"),
            callback_data=SettingsCB(action="notifications").pack(),
        )
    )
    if len(locales) > 1:
        builder.row(
            *[
                InlineKeyboardButton(
                    text=code.upper(),
                    callback_data=SettingsCB(action="language", value=code).pack(),
                )
                for code in locales
            ]
        )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale), callback_data=Nav(to="profile").pack()
        )
    )
    return builder.as_markup()


def help_menu(texts: Texts, locale: str | None, support_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    topics = [
        ("buy", "📱 How to buy a number"),
        ("payment", "💳 Payment help"),
        ("no_sms", "📩 SMS not received"),
        ("refund", "💰 Refund policy"),
        ("terms", "📄 Terms of Service"),
        ("privacy", "🔐 Privacy Policy"),
    ]
    for key, label in topics:
        builder.row(InlineKeyboardButton(text=label, callback_data=HelpCB(topic=key).pack()))
    if support_url:
        builder.row(InlineKeyboardButton(text=texts.button("support", locale), url=support_url))
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        )
    )
    return builder.as_markup()
