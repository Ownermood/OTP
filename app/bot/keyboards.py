"""Keyboard builders.

Every inline keyboard in the bot is built here, so navigation stays consistent:
long lists are paginated with the same control row, and every screen below the
main menu ends with Back and/or Home.
"""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    ConfirmCB,
    CountryCB,
    FavoriteCB,
    HelpCB,
    Nav,
    NoopCB,
    OrderCB,
    OrdersListCB,
    PaymentCB,
    RentalCB,
    ServiceCB,
    SettingsCB,
    SmmCB,
    WalletCB,
)
from app.bot.texts import Texts
from app.core.constants import GRID_COLUMNS, RENTAL_PRESET_HOURS
from app.core.money import format_money
from app.utils.formatting import availability_icon, order_icon, truncate
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


def main_menu(texts: Texts, locale: str | None, smm_enabled: bool) -> InlineKeyboardMarkup:
    """The home screen. One primary action, then pairs."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=texts.button("buy", locale), callback_data=Nav(to="buy").pack()
        )
    )
    second_row = [
        InlineKeyboardButton(
            text=texts.button("rent", locale), callback_data=Nav(to="rent").pack()
        ),
        InlineKeyboardButton(
            text=texts.button("orders", locale), callback_data=Nav(to="orders").pack()
        ),
    ]
    builder.row(*second_row)
    if smm_enabled:
        builder.row(
            InlineKeyboardButton(
                text=texts.button("smm", locale), callback_data=Nav(to="smm").pack()
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("profile", locale), callback_data=Nav(to="profile").pack()
        ),
        InlineKeyboardButton(
            text=texts.button("favorites", locale), callback_data=Nav(to="favorites").pack()
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("wallet", locale), callback_data=Nav(to="wallet").pack()
        ),
        InlineKeyboardButton(
            text=texts.button("referral", locale), callback_data=Nav(to="referral").pack()
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("help", locale), callback_data=Nav(to="help").pack()
        )
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


def rental_durations(
    texts: Texts, locale: str | None, token: str, minimum: int, maximum: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    presets = [h for h in RENTAL_PRESET_HOURS if minimum <= h <= maximum]
    for chunk in _chunks(presets, 3):
        builder.row(
            *[
                InlineKeyboardButton(
                    text=(f"{h}h" if h < 24 else f"{h // 24}d"),
                    callback_data=RentalCB(token=token, hours=h).pack(),
                )
                for h in chunk
            ]
        )
    builder.row(
        InlineKeyboardButton(
            text="⚙️ Custom", callback_data=RentalCB(token=token, hours=0).pack()
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


def orders_root(texts: Texts, locale: str | None, smm_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📱 SMS Activations", callback_data=OrdersListCB(kind="activation").pack()
        )
    )
    builder.row(
        InlineKeyboardButton(text="⏳ Rentals", callback_data=OrdersListCB(kind="rental").pack())
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
                text=texts.button("buy_now", locale), callback_data=CountryCB(token=token).pack()
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("remove", locale),
            callback_data=FavoriteCB(action="remove", favorite_id=favorite_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("back", locale), callback_data=Nav(to="favorites").pack()
        )
    )
    return builder.as_markup()


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
                    text=label, callback_data=WalletCB(action=f"history:{key}").pack()
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
            text=texts.button("search", locale), callback_data=SmmCB(action="search").pack()
        )
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
    texts: Texts, locale: str | None, page: Page, category: str, currency: str
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
            text="🔄 Track Status", callback_data=SmmCB(action="track", value=str(order_id)).pack()
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("home", locale), callback_data=Nav(to="home").pack()
        )
    )
    return builder.as_markup()


def order_detail(
    texts: Texts, locale: str | None, order, back_kind: str
) -> InlineKeyboardMarkup:
    """Controls for one order; cancel only shows while the order is still open."""
    from app.core.constants import OrderStatus

    builder = InlineKeyboardBuilder()
    if not OrderStatus(order.status).is_final:
        builder.row(
            InlineKeyboardButton(
                text=texts.button("refresh", locale),
                callback_data=OrderCB(action="refresh", order_id=order.id).pack(),
            ),
            InlineKeyboardButton(
                text=texts.button("cancel", locale),
                callback_data=OrderCB(action="cancel", order_id=order.id).pack(),
            ),
        )
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


def confirm_or_cancel(
    texts: Texts, locale: str | None, confirm_callback: str, cancel_to: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=texts.button("confirm", locale), callback_data=confirm_callback)
    )
    builder.row(
        InlineKeyboardButton(
            text=texts.button("cancel", locale), callback_data=Nav(to=cancel_to).pack()
        )
    )
    return builder.as_markup()


def _chunks(items: list, size: int) -> list[list]:
    return [items[index : index + size] for index in range(0, len(items), size)]
