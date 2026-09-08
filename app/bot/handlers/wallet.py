"""Wallet: balance, deposits, transaction history, promo codes, transfers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from app.bot import keyboards
from app.bot.callbacks import Nav, PaymentCB, WalletCB
from app.bot.handlers.common import Context, build_context, show, toast
from app.bot.states import PaymentStates, PromoStates, TransferStates
from app.core.constants import PaymentStatus, TransactionType
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.core.money import format_money, parse_amount, to_minor
from app.utils.formatting import format_countdown, format_datetime
from app.utils.pagination import paginate
from app.utils.validators import parse_promo_code, parse_username

router = Router(name="wallet")
logger = get_logger(__name__)

#: Display names for the payment methods, keyed by provider name.
METHOD_LABELS = {"cryptobot": "🩵 Crypto", "telegram_stars": "⭐ Telegram Stars"}

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


@router.callback_query(WalletCB.filter(F.action == "deposit"))
async def choose_method(query: CallbackQuery, **data):
    context = build_context(data)
    methods = {
        name: METHOD_LABELS.get(name, name.title()) for name in context.payments.available
    }
    await show(
        query,
        context.text("wallet.select_method"),
        keyboards.payment_methods(context.texts, context.locale, methods),
    )


@router.callback_query(PaymentCB.filter(F.action == "method"))
async def prompt_amount(query: CallbackQuery, callback_data: PaymentCB, state: FSMContext, **data):
    context = build_context(data)
    context.payments.provider(callback_data.provider)  # validates it is enabled
    await state.set_state(PaymentStates.entering_amount)
    await state.update_data(provider=callback_data.provider)
    await show(
        query,
        context.text(
            "wallet.enter_amount",
            minimum=context.money(to_minor(context.settings.min_deposit)),
            maximum=context.money(to_minor(context.settings.max_deposit)),
        ),
        keyboards.back_home(context.texts, context.locale, back_to="wallet"),
    )


@router.message(PaymentStates.entering_amount)
async def create_invoice(message: Message, state: FSMContext, **data):
    """Create the invoice. Native providers (Stars) get Telegram's own checkout."""
    context = build_context(data)
    amount = parse_amount(message.text or "")
    if amount is None:
        raise ValidationError("unparseable amount")
    context.payments.validate_amount(amount)

    provider_name = (await state.get_data()).get("provider", "")
    await state.clear()

    payment = await context.payments.create_invoice(message.from_user.id, provider_name, amount)
    provider = context.payments.provider(provider_name)

    if provider.is_native:
        await _send_stars_invoice(message, context, payment, provider)
        return

    await show(
        message,
        context.text(
            "wallet.invoice",
            amount=context.money(payment.amount),
            method=METHOD_LABELS.get(provider_name, provider_name),
            provider_amount=payment.provider_amount,
            countdown=format_countdown(payment.expires_at),
        ),
        keyboards.invoice(context.texts, context.locale, payment.id, payment.pay_url or ""),
    )


async def _send_stars_invoice(message: Message, context: Context, payment, provider) -> None:
    """Telegram Stars checkout: the invoice id travels as the payload."""
    stars = int(payment.provider_amount)
    if stars > provider.max_stars:
        raise ValidationError("amount exceeds the Telegram Stars limit")

    await message.answer_invoice(
        title=f"{context.settings.service_name} — balance top-up",
        description=f"Add {context.money(payment.amount)} to your balance",
        payload=payment.invoice_id,
        currency="XTR",
        prices=[LabeledPrice(label="Top-up", amount=stars)],
    )


@router.pre_checkout_query()
async def approve_checkout(pre_checkout: PreCheckoutQuery) -> None:
    """Telegram requires an answer within 10 seconds; nothing to validate here."""
    await pre_checkout.answer(ok=True)


@router.message(F.successful_payment)
async def stars_paid(message: Message, **data):
    """Settle a Stars payment.

    The payload is the invoice id, and settlement is keyed on it, so Telegram
    re-delivering this update cannot credit the balance twice.
    """
    context = build_context(data)
    invoice_id = message.successful_payment.invoice_payload
    settlement = await context.payments.settle("telegram_stars", invoice_id)
    if settlement is None:
        logger.warning("stars.unknown_payload", payload=invoice_id)
        return

    await message.answer(
        context.text(
            "wallet.success",
            amount=context.money(settlement.payment.amount),
            balance=context.money(settlement.balance_after),
        ),
        reply_markup=keyboards.main_menu(context.texts, context.locale, context.smm.enabled),
    )


@router.callback_query(PaymentCB.filter(F.action == "check"))
async def check_payment(query: CallbackQuery, callback_data: PaymentCB, **data):
    """Manual 'has it landed yet' check, alongside the background poller."""
    context = build_context(data)
    payments = await context.payments.list_for_user(query.from_user.id)
    payment = next((p for p in payments if p.id == callback_data.payment_id), None)
    if payment is None:
        await toast(query, context.text("errors.order_not_found"), alert=True)
        return

    if payment.status == PaymentStatus.PAID:
        await _payment_settled(query, context, payment.amount)
        return

    provider = context.payments.provider(payment.provider)
    status = await provider.check_payment(payment.invoice_id)
    if status != "paid":
        await toast(query, context.text("common.loading"))
        return

    settlement = await context.payments.settle(payment.provider, payment.invoice_id)
    if settlement is not None:
        await _payment_settled(query, context, settlement.payment.amount)


@router.callback_query(PaymentCB.filter(F.action == "cancel"))
async def cancel_invoice(query: CallbackQuery, callback_data: PaymentCB, **data):
    context = build_context(data)
    payments = await context.payments.list_for_user(query.from_user.id)
    payment = next((p for p in payments if p.id == callback_data.payment_id), None)
    if payment is not None and payment.status == PaymentStatus.PENDING:
        provider = context.payments.provider(payment.provider)
        await provider.cancel_invoice(payment.invoice_id)
        await context.payments.mark_failed(payment, PaymentStatus.EXPIRED)
    await show(
        query,
        context.text("wallet.main", balance=context.money(context.user.balance)),
        keyboards.wallet(context.texts, context.locale, context.settings.transfer_enabled),
    )


async def _payment_settled(query: CallbackQuery, context: Context, amount: int) -> None:
    balance = await context.wallet.get_balance(query.from_user.id)
    await show(
        query,
        context.text("wallet.success", amount=context.money(amount), balance=context.money(balance)),
        keyboards.back_home(context.texts, context.locale, back_to="wallet"),
    )


# -- history ----------------------------------------------------------------


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


@router.callback_query(WalletCB.filter(F.action == "transfer"))
async def prompt_transfer_user(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    if not context.settings.transfer_enabled:
        await toast(query, context.text("errors.invalid_input"), alert=True)
        return
    await state.set_state(TransferStates.entering_username)
    await show(
        query,
        context.text("wallet.transfer_user"),
        keyboards.back_home(context.texts, context.locale, back_to="wallet"),
    )


@router.message(TransferStates.entering_username)
async def enter_transfer_user(message: Message, state: FSMContext, **data):
    context = build_context(data)
    username = parse_username(message.text or "")
    await state.set_state(TransferStates.entering_amount)
    await state.update_data(recipient=username)
    await show(
        message,
        context.text(
            "wallet.transfer_amount",
            username=username,
            balance=context.money(context.user.balance),
        ),
        keyboards.back_home(context.texts, context.locale, back_to="wallet"),
    )


@router.message(TransferStates.entering_amount)
async def do_transfer(message: Message, state: FSMContext, **data):
    context = build_context(data)
    amount = parse_amount(message.text or "")
    if amount is None:
        raise ValidationError("unparseable amount")

    username = (await state.get_data()).get("recipient", "")
    await state.clear()
    recipient = await context.users.transfer(message.from_user.id, username, amount)
    balance = await context.wallet.get_balance(message.from_user.id)

    await show(
        message,
        context.text(
            "wallet.transfer_done",
            amount=context.money(amount),
            username=username,
            balance=context.money(balance),
        ),
        keyboards.back_home(context.texts, context.locale, back_to="wallet"),
    )
    await data["notifications"].notify_user(
        recipient.id,
        context.text(
            "wallet.transfer_received",
            amount=context.money(amount),
            balance=context.money(recipient.balance),
        ),
        essential=True,
    )
