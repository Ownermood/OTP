"""Gateway deposits: choosing a method, invoices and settlement.

Manually reviewed UPI and bank deposits live in
:mod:`app.bot.handlers.manual_payments`; this module covers the automated
gateways and Telegram Stars.
"""

from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from app.bot import keyboards
from app.bot.ack import acknowledge
from app.bot.callbacks import PaymentCB, WalletCB
from app.bot.handlers.common import Context, build_context, show, toast
from app.bot.handlers.wallet import METHOD_LABELS, router
from app.bot.states import PaymentStates
from app.core.constants import QUICK_DEPOSIT_AMOUNTS, PaymentStatus
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.core.money import parse_amount, to_minor
from app.utils.formatting import format_countdown

logger = get_logger(__name__)

@router.callback_query(WalletCB.filter(F.action == "deposit"))
async def choose_method(query: CallbackQuery, **data):
    context = build_context(data)
    methods = {
        name: METHOD_LABELS.get(name, name.title()) for name in context.payments.available
    }
    if context.settings.manual_payment_enabled:
        # Reviewed by a human rather than a gateway, so it has no provider entry.
        methods["manual"] = METHOD_LABELS["manual"]
    await show(
        query,
        context.text("wallet.select_method"),
        keyboards.payment_methods(context.texts, context.locale, methods),
    )


# Explicitly not "manual": that method has no gateway and is handled in
# app/bot/handlers/manual_payments.py. Stated here so the two do not depend on
# router registration order.


@router.callback_query(PaymentCB.filter((F.action == "method") & (F.provider != "manual")))
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
        keyboards.amount_prompt(
            context.texts,
            context.locale,
            callback_data.provider,
            context.settings.currency_symbol,
            back_to="wallet",
        ),
    )


@router.message(PaymentStates.entering_amount)
async def create_invoice(message: Message, state: FSMContext, **data):
    """Create the invoice. Native providers (Stars) get Telegram's own checkout."""
    context = build_context(data)
    amount = parse_amount(message.text or "")
    if amount is None:
        raise ValidationError("unparseable amount")

    provider_name = (await state.get_data()).get("provider", "")
    await _finalize_deposit(message, context, state, provider_name, amount)


@router.callback_query(
    PaymentCB.filter((F.action.in_(QUICK_DEPOSIT_AMOUNTS)) & (F.provider != "manual"))
)
async def quick_amount(query: CallbackQuery, callback_data: PaymentCB, state: FSMContext, **data):
    """A one-tap shortcut for the amount prompt -- never a different code path.

    The callback carries only a preset *key*; the amount itself always comes
    from the server-side QUICK_DEPOSIT_AMOUNTS table, and is still validated
    exactly like a typed amount would be.
    """
    context = build_context(data)
    amount = to_minor(QUICK_DEPOSIT_AMOUNTS[callback_data.action])
    await _finalize_deposit(query, context, state, callback_data.provider, amount)


async def _finalize_deposit(
    event: Message | CallbackQuery, context: Context, state: FSMContext, provider_name: str, amount: int
) -> None:
    context.payments.validate_amount(amount)
    await state.clear()

    user_id = event.from_user.id
    payment = await context.payments.create_invoice(user_id, provider_name, amount)
    provider = context.payments.provider(provider_name)

    if provider.is_native:
        await _send_stars_invoice(event, context, payment, provider)
        return

    await show(
        event,
        context.text(
            "wallet.invoice",
            amount=context.money(payment.amount),
            method=METHOD_LABELS.get(provider_name, provider_name),
            provider_amount=payment.provider_amount,
            countdown=format_countdown(payment.expires_at),
        ),
        keyboards.invoice(context.texts, context.locale, payment.id, payment.pay_url or ""),
    )


async def _send_stars_invoice(
    event: Message | CallbackQuery, context: Context, payment, provider
) -> None:
    """Telegram Stars checkout: the invoice id travels as the payload."""
    stars = int(payment.provider_amount)
    if stars > provider.max_stars:
        raise ValidationError("amount exceeds the Telegram Stars limit")

    if isinstance(event, CallbackQuery):
        await acknowledge(event)
        message = event.message
    else:
        message = event
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
