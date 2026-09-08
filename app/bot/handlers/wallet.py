"""Wallet: balance, transaction history and promo redemption.

The router lives here; deposits and transfers register on it from their own
modules, so the wallet is one router however many files it spans.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards
from app.bot.callbacks import Nav, WalletCB
from app.bot.handlers.common import build_context, show
from app.bot.states import PromoStates
from app.core.constants import TransactionType
from app.core.logging import get_logger
from app.core.money import format_money
from app.utils.formatting import format_datetime
from app.utils.pagination import paginate
from app.utils.validators import parse_promo_code

router = Router(name="wallet")
logger = get_logger(__name__)

#: Display names for the payment methods, keyed by provider name.
METHOD_LABELS = {
    "cryptobot": "🩵 Crypto",
    "telegram_stars": "⭐ Telegram Stars",
    "manual": "📲 UPI / QR",
}

#: History filter -> transaction types.
HISTORY_FILTERS = {
    "all": None,
    "deposit": (TransactionType.DEPOSIT,),
    "purchase": (TransactionType.PURCHASE,),
    "refund": (TransactionType.REFUND,),
    "referral": (TransactionType.REFERRAL,),
}

TYPE_ICONS = {
    TransactionType.DEPOSIT: "➕",
    TransactionType.PURCHASE: "🛍",
    TransactionType.REFUND: "↩️",
    TransactionType.REFERRAL: "🎁",
    TransactionType.PROMO: "🎟",
    TransactionType.TRANSFER_IN: "📥",
    TransactionType.TRANSFER_OUT: "📤",
    TransactionType.ADMIN_ADJUSTMENT: "🛠",
}

@router.callback_query(Nav.filter(F.to == "wallet"))
async def open_wallet(query: CallbackQuery, state: FSMContext, **data):
    await state.clear()
    context = build_context(data)
    await show(
        query,
        context.text("wallet.main", balance=context.money(context.user.balance)),
        keyboards.wallet(context.texts, context.locale, context.settings.transfer_enabled),
    )


# -- deposits ---------------------------------------------------------------


@router.callback_query(WalletCB.filter(F.action.startswith("history")))
async def history(query: CallbackQuery, callback_data: WalletCB, **data):
    context = build_context(data)
    _, _, filter_key = callback_data.action.partition("_")
    types = HISTORY_FILTERS.get(filter_key or "all")
    transactions = await context.users.transactions(query.from_user.id, types)

    if not transactions:
        await show(
            query,
            context.text("wallet.history_empty"),
            keyboards.back_home(context.texts, context.locale, back_to="wallet"),
        )
        return

    page = paginate(transactions, callback_data.page, per_page=10)
    lines = [
        f"{TYPE_ICONS.get(TransactionType(t.type), '•')} "
        f"<b>{format_money(t.amount, context.settings.currency_symbol)}</b> — "
        f"{t.description or TransactionType(t.type).value.title()}\n"
        f"<i>{format_datetime(t.created_at)}</i>"
        for t in page.items
    ]
    await show(
        query,
        context.text("wallet.history", count=len(transactions)) + "\n\n" + "\n\n".join(lines),
        keyboards.transactions_filters(context.texts, context.locale, page),
    )


# -- promo ------------------------------------------------------------------


@router.callback_query(WalletCB.filter(F.action == "promo"))
async def prompt_promo(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    await state.set_state(PromoStates.entering_code)
    await show(
        query,
        context.text("promo.prompt"),
        keyboards.back_home(context.texts, context.locale, back_to="wallet"),
    )


@router.message(PromoStates.entering_code)
async def redeem_promo(message: Message, state: FSMContext, **data):
    context = build_context(data)
    code = parse_promo_code(message.text or "")
    await state.clear()
    redemption = await context.promo.redeem(message.from_user.id, code)

    if redemption.deferred:
        # A percent promo pays out against the next deposit, not right now.
        text = context.text("promo.armed", code=redemption.code, percent=redemption.percent)
    else:
        text = context.text(
            "promo.success",
            code=redemption.code,
            amount=context.money(redemption.amount),
            balance=context.money(redemption.balance_after),
        )

    await show(message, text, keyboards.back_home(context.texts, context.locale, back_to="wallet"))


# -- transfers --------------------------------------------------------------
