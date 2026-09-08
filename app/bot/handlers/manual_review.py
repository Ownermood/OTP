"""Manual deposits: the reviewer's side.

Approve and Decline are tapped from the review channel. Whether the tapper may
decide anything is resolved from the configured admin roles on every tap --
the buttons are visible to everyone who can see the channel.
"""

from __future__ import annotations

from aiogram import F
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import ManualCB
from app.bot.handlers.common import Context, build_context, toast
from app.bot.handlers.manual_payments import _service, router
from app.bot.states import ManualPaymentStates
from app.core.exceptions import AccessDeniedError
from app.core.logging import get_logger

logger = get_logger(__name__)

@router.callback_query(ManualCB.filter(F.action == "approve"))
async def approve(query: CallbackQuery, callback_data: ManualCB, **data):
    context = build_context(data)
    manual = _service(context)

    decision = await manual.approve(callback_data.payment_id, query.from_user.id)
    if not decision.applied:
        await toast(query, context.text("wallet.manual_already_reviewed"), alert=True)
        await _close_review(query, context, decision, reviewer=query.from_user)
        return

    await _close_review(query, context, decision, reviewer=query.from_user)
    await data["notifications"].notify_user(
        decision.payment.user_id,
        context.text(
            "wallet.manual_approved",
            request_id=decision.payment.id,
            amount=context.money(decision.payment.amount),
            balance=context.money(decision.balance_after),
        ),
        essential=True,
    )


@router.callback_query(ManualCB.filter(F.action == "decline"))
async def prompt_decline(query: CallbackQuery, callback_data: ManualCB, state: FSMContext, **data):
    """Ask for a reason, so the user is told something useful."""
    context = build_context(data)
    manual = _service(context)
    if not manual.can_review(query.from_user.id):
        raise AccessDeniedError("not a payment reviewer")

    await state.set_state(ManualPaymentStates.declining)
    await state.update_data(decline_payment_id=callback_data.payment_id)
    await query.answer()
    await query.bot.send_message(
        query.from_user.id,
        context.text("wallet.manual_decline_reason", request_id=callback_data.payment_id),
    )


@router.message(ManualPaymentStates.declining)
async def do_decline(message: Message, state: FSMContext, **data):
    context = build_context(data)
    manual = _service(context)

    stored = await state.get_data()
    await state.clear()
    payment_id = int(stored.get("decline_payment_id", 0))
    reason = (message.text or "").strip()

    decision = await manual.decline(payment_id, message.from_user.id, reason)
    if not decision.applied:
        await message.answer(context.text("wallet.manual_already_reviewed"))
        return

    await _edit_review_post(message.bot, context, decision, message.from_user)
    await message.answer(
        context.text("wallet.manual_decline_done", request_id=payment_id, reason=reason)
    )
    await data["notifications"].notify_user(
        decision.payment.user_id,
        context.text(
            "wallet.manual_declined",
            request_id=decision.payment.id,
            amount=context.money(decision.payment.amount),
            reason=reason or "—",
        ),
        essential=True,
    )


async def _close_review(query: CallbackQuery, context: Context, decision, reviewer) -> None:
    """Rewrite the channel post so the outcome and reviewer are on the record."""
    verdict = context.text(
        "wallet.manual_verdict_approved" if decision.approved else "wallet.manual_verdict_declined",
        reviewer=f"@{reviewer.username}" if reviewer.username else str(reviewer.id),
        request_id=decision.payment.id,
    )
    try:
        if query.message is not None:
            await query.message.edit_caption(
                caption=f"{query.message.caption}\n\n{verdict}", reply_markup=None
            )
    except TelegramAPIError as exc:
        logger.debug("manual_payment.caption_edit_failed", error=str(exc))


async def _edit_review_post(bot, context: Context, decision, reviewer) -> None:
    """Same, for a decision made over DM rather than on the post itself."""
    payment = decision.payment
    if not payment.review_message_id:
        return
    verdict = context.text(
        "wallet.manual_verdict_declined",
        reviewer=f"@{reviewer.username}" if reviewer.username else str(reviewer.id),
        request_id=payment.id,
    )
    try:
        await bot.edit_message_reply_markup(
            chat_id=context.settings.manual_payment_channel_id,
            message_id=payment.review_message_id,
            reply_markup=None,
        )
        await bot.send_message(
            chat_id=context.settings.manual_payment_channel_id,
            text=verdict,
            reply_to_message_id=payment.review_message_id,
        )
    except TelegramAPIError as exc:
        logger.debug("manual_payment.review_edit_failed", error=str(exc))
