"""Handler helpers.

Two jobs: build the per-update service objects from the session the middleware
opened, and edit-or-send screens so navigating the bot rewrites one message
instead of flooding the chat.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.texts import Texts
from app.core.config import Settings
from app.core.money import format_money
from app.services.admin import AdminService
from app.services.catalog import CatalogService
from app.services.orders import OrderService
from app.services.payments import PaymentService
from app.services.pricing import PricingService
from app.services.promo import PromoService
from app.services.referrals import ReferralService
from app.services.smm import SmmService
from app.services.users import UserService
from app.services.wallet import WalletService


@dataclass(slots=True)
class Context:
    """Everything a handler needs, assembled once per update."""

    session: AsyncSession
    settings: Settings
    texts: Texts
    locale: str
    user: Any
    wallet: WalletService
    users: UserService
    orders: OrderService
    payments: PaymentService
    referrals: ReferralService
    promo: PromoService
    smm: SmmService
    admin: AdminService
    catalog: CatalogService
    tokens: Any
    admin_role: Any

    def money(self, minor: int) -> str:
        return format_money(minor, self.settings.currency_symbol)

    def text(self, key: str, **values: Any) -> str:
        return self.texts.get(key, self.locale, **values)

    def button(self, name: str) -> str:
        return self.texts.button(name, self.locale)


def build_context(data: dict[str, Any]) -> Context:
    """Assemble a :class:`Context` from middleware-provided data."""
    session: AsyncSession = data["session"]
    settings: Settings = data["settings"]
    wallet: WalletService = data["wallet"]
    pricing: PricingService = data["pricing"]
    referrals = ReferralService(session, wallet, settings)

    return Context(
        session=session,
        settings=settings,
        texts=data["texts"],
        locale=data.get("locale") or settings.locale,
        user=data.get("user"),
        wallet=wallet,
        users=data["users"],
        orders=OrderService(session, data["sms_provider"], pricing, wallet, settings),
        payments=PaymentService(
            session, data["payment_providers"], wallet, referrals, settings
        ),
        referrals=referrals,
        promo=PromoService(session, wallet),
        smm=SmmService(
            session,
            data["smm_provider"],
            pricing,
            wallet,
            settings,
            data.get("smm_cache"),
        ),
        admin=AdminService(session, wallet),
        catalog=data["catalog"],
        tokens=data["tokens"],
        admin_role=data.get("admin_role"),
    )


async def show(
    event: Message | CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
    force_new: bool = False,
) -> None:
    """Render a screen.

    Callbacks edit the message in place -- the spec's "prefer editing existing
    messages" rule -- and fall back to sending a new one when Telegram refuses
    (too old to edit, or the content is identical).
    """
    if isinstance(event, CallbackQuery):
        await event.answer()
        if event.message is None:
            return
        if not force_new:
            try:
                await event.message.edit_text(text, reply_markup=keyboard)
                return
            except TelegramBadRequest as exc:
                if "message is not modified" in str(exc):
                    return
        await event.message.answer(text, reply_markup=keyboard)
    else:
        await event.answer(text, reply_markup=keyboard)


async def toast(event: Message | CallbackQuery, text: str, alert: bool = False) -> None:
    """A brief acknowledgement that does not replace the current screen."""
    if isinstance(event, CallbackQuery):
        await event.answer(text, show_alert=alert)
    else:
        await event.answer(text)
