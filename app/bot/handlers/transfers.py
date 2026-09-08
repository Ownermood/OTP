"""Balance transfers between users.

Quoted and confirmed before anything moves: a transfer cannot be undone, and
the confirmation carries a single-use token so one tap counts once.
"""

from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards
from app.bot.callbacks import TransferCB, WalletCB
from app.bot.handlers.common import build_context, show, toast
from app.bot.handlers.wallet import router
from app.bot.states import TransferStates
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.core.money import parse_amount
from app.utils.validators import parse_username

logger = get_logger(__name__)

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
async def confirm_transfer(message: Message, state: FSMContext, **data):
    """Quote the transfer. Money moves only on the confirmation below."""
    context = build_context(data)
    amount = parse_amount(message.text or "")
    if amount is None:
        raise ValidationError("unparseable amount")

    stored = await state.get_data()
    username = stored.get("recipient", "")
    if not username:
        await state.clear()
        raise ValidationError("transfer expired")

    # Single-use token, so a double-tapped confirm cannot send twice.
    token = context.tokens.issue(
        message.from_user.id, kind="transfer", username=username, amount=amount
    )
    await state.clear()
    await show(
        message,
        context.text(
            "wallet.transfer_confirm", username=username, amount=context.money(amount)
        ),
        keyboards.confirm_or_cancel(
            context.texts, context.locale, TransferCB(token=token).pack(), "wallet"
        ),
    )


@router.callback_query(TransferCB.filter())
async def do_transfer(query: CallbackQuery, callback_data: TransferCB, **data):
    """Perform a confirmed transfer. The token is single-use, so one tap counts."""
    context = build_context(data)
    payload = context.tokens.consume(callback_data.token, query.from_user.id)
    if payload is None:
        await toast(query, context.text("errors.duplicate_operation"), alert=True)
        return

    username = payload["username"]
    amount = payload["amount"]
    recipient = await context.users.transfer(query.from_user.id, username, amount)
    balance = await context.wallet.get_balance(query.from_user.id)

    await show(
        query,
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
