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
from app.bot.keyboards.style import DANGER, PRIMARY, SUCCESS, button
from app.bot.texts import Texts
from app.core.constants import QUICK_DEPOSIT_AMOUNTS
from app.core.money import format_money, to_minor
from app.utils.pagination import Page


def profile(texts: Texts, locale: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("deposit", locale),
            icon_custom_emoji_id=texts.icon("deposit"),
            callback_data=WalletCB(action="deposit").pack(),
            style=PRIMARY,
        ),
        InlineKeyboardButton(
            text=texts.button("orders", locale),
            icon_custom_emoji_id=texts.icon("orders"),
            callback_data=Nav(to="orders").pack(),
            style=PRIMARY,
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("referral", locale),
            icon_custom_emoji_id=texts.icon("referral"),
            callback_data=Nav(to="referral").pack(),
            style=PRIMARY,
        ),
        InlineKeyboardButton(
            text=texts.button("favorites", locale),
            callback_data=Nav(to="favorites").pack(),
            style=PRIMARY,
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("promo", locale),
            callback_data=WalletCB(action="promo").pack(),
            style=PRIMARY,
        ),
        InlineKeyboardButton(
            text=texts.button("settings", locale),
            callback_data=Nav(to="settings").pack(),
            style=PRIMARY,
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


def wallet(texts: Texts, locale: str | None, transfer_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("deposit", locale),
            icon_custom_emoji_id=texts.icon("deposit"),
            callback_data=WalletCB(action="deposit").pack(),
            style=PRIMARY,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("history", locale),
            callback_data=WalletCB(action="history").pack(),
            style=PRIMARY,
        ),
        InlineKeyboardButton(
            text=texts.button("promo", locale),
            callback_data=WalletCB(action="promo").pack(),
            style=PRIMARY,
        ),
    )
    if transfer_enabled:
        builder.row(
            InlineKeyboardButton(
                text=texts.button("transfer", locale),
                callback_data=WalletCB(action="transfer").pack(),
                style=PRIMARY,
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


def payment_methods(
    texts: Texts, locale: str | None, providers: dict[str, str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for name, label in providers.items():
        builder.row(
            InlineKeyboardButton(
                text=label,
                icon_custom_emoji_id=texts.icon("payment"),
                callback_data=PaymentCB(action="method", provider=name).pack(),
                style=PRIMARY,
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale),
            icon_custom_emoji_id=texts.icon("back"),
            callback_data=Nav(to="wallet").pack(),
        )
    )
    return builder.as_markup()


def amount_prompt(
    texts: Texts, locale: str | None, provider: str, currency_symbol: str, back_to: str = "wallet"
) -> InlineKeyboardMarkup:
    """The enter-amount screen: manual typing is the primary path, these are shortcuts."""
    builder = InlineKeyboardBuilder()
    quick_buttons = [
        InlineKeyboardButton(
            text=format_money(to_minor(major), currency_symbol),
            callback_data=PaymentCB(action=action, provider=provider).pack(),
            style=PRIMARY,
        )
        for action, major in QUICK_DEPOSIT_AMOUNTS.items()
    ]
    for row in _chunks(quick_buttons, 3):
        builder.row(*row)
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale),
            icon_custom_emoji_id=texts.icon("back"),
            callback_data=Nav(to=back_to).pack(),
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


def invoice(
    texts: Texts, locale: str | None, payment_id: int, pay_url: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if pay_url:
        builder.row(
            InlineKeyboardButton(
                text=texts.button("pay", locale),
                icon_custom_emoji_id=texts.icon("payment"),
                url=pay_url,
                style=SUCCESS,
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("check_payment", locale),
            icon_custom_emoji_id=texts.icon("refresh"),
            callback_data=PaymentCB(action="check", payment_id=payment_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("cancel", locale),
            icon_custom_emoji_id=texts.icon("cancel"),
            callback_data=PaymentCB(action="cancel", payment_id=payment_id).pack(), style=DANGER,
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
            text=texts.button("back", locale),
            icon_custom_emoji_id=texts.icon("back"),
            callback_data=Nav(to="wallet").pack(),
        )
    )
    return builder.as_markup()


def referral(
    texts: Texts, locale: str | None, share_url: str, link: str | None = None
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("share", locale),
            icon_custom_emoji_id=texts.icon("referral"),
            url=share_url,
            style=PRIMARY,
        )
    )
    if link:
        # A tap-to-copy button beats making the user select/retype the link.
        builder.row(button(texts.button("copy_link", locale), copy=link))
    builder.row(
        InlineKeyboardButton(
            text=texts.button("history", locale),
            callback_data=Nav(to="referral_history").pack(),
            style=PRIMARY,
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


def settings_menu(
    texts: Texts, locale: str | None, notifications: bool, locales: Sequence[str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=("🔔 Notifications: ON" if notifications else "🔕 Notifications: OFF"),
            callback_data=SettingsCB(action="notifications").pack(),
            style=PRIMARY,
        )
    )
    if len(locales) > 1:
        builder.row(
            *[
                InlineKeyboardButton(
                    text=code.upper(),
                    callback_data=SettingsCB(action="language", value=code).pack(),
                    style=PRIMARY,
                )
                for code in locales
            ]
        )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale),
            icon_custom_emoji_id=texts.icon("back"),
            callback_data=Nav(to="profile").pack(),
        )
    )
    return builder.as_markup()


def help_menu(texts: Texts, locale: str | None, support_url: str) -> InlineKeyboardMarkup:
    """Categorised help topics, grouped the way a user actually thinks about
    them: how things work, then troubleshooting, then policy fine print."""
    builder = InlineKeyboardBuilder()
    topics = [
        ("buy", "How to Buy"),
        ("payment", "Payment / Deposit"),
        ("orders", "OTP / Orders"),
        ("referral", "Referral"),
        ("account", "Account / Balance"),
        ("troubleshooting", "Troubleshooting"),
    ]
    for key, label in topics:
        builder.row(
            InlineKeyboardButton(
                text=label, icon_custom_emoji_id=texts.icon("help"), callback_data=HelpCB(topic=key).pack()
            )
        )
    policies = [
        ("refund", "Refund Policy"),
        ("terms", "Terms of Service"),
        ("privacy", "Privacy Policy"),
    ]
    for chunk in _chunks(
        [
            InlineKeyboardButton(
                text=label,
                icon_custom_emoji_id=texts.icon("help"),
                callback_data=HelpCB(topic=key).pack(),
            )
            for key, label in policies
        ],
        3,
    ):
        builder.row(*chunk)
    if support_url:
        builder.row(
            InlineKeyboardButton(
                text=texts.button("support", locale),
                icon_custom_emoji_id=texts.icon("support"),
                url=support_url,
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
