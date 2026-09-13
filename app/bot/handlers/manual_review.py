"""Manual deposits: the reviewer's side.

Approve and Decline are tapped from the review channel. Whether the tapper may
decide anything is resolved from the configured admin roles on every tap --
the buttons are visible to everyone who can see the channel.
"""

from __future__ import annotations

from aiogram import F
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import ManualCB
from app.bot.handlers.common import Context, build_context, show, toast
from app.bot.handlers.manual_payments import (
    _review_caption,
    _service,
    decision_keyboard,
    post_for_review,
    router,
)
from app.bot.keyboards.style import SUCCESS
from app.bot.states import ManualPaymentStates
from app.core.constants import PaymentStatus
from app.core.exceptions import AccessDeniedError
from app.core.logging import get_logger
from app.services.admin import require
from app.utils.quotes import build_reply_parameters

logger = get_logger(__name__)

@router.callback_query(ManualCB.filter(F.action == "open"))
async def open_request(query: CallbackQuery, callback_data: ManualCB, **data):
    """Show one pending request with its proof, and the two decisions.

    Reached from the admin panel when the review channel is not an option.
    Viewing only needs "payments" -- the same permission the pending list
    already requires. Actually deciding (approve/decline) still requires
    "balance", checked separately by those handlers: SUPPORT can read this
    screen but not credit from it.
    """
    context = build_context(data)
    require(context.admin_role, "payments")
    manual = _service(context)

    payment = await manual.get(callback_data.payment_id)
    if payment is None:
        await toast(query, context.text("errors.order_not_found"), alert=True)
        return

    missing_notification = payment.review_message_id is None
    caption = await _review_caption(context, payment)
    if missing_notification:
        caption += "\n\n" + context.text("wallet.manual_review_missing_notice")
    keyboard = decision_keyboard(context.texts, payment.id, missing_notification)

    await query.answer()
    if payment.proof_file_id and query.message is not None:
        try:
            await query.message.answer_photo(payment.proof_file_id, caption=caption, reply_markup=keyboard)
            return
        except TelegramAPIError as exc:
            # A stale/invalid file id (e.g. from before a bot token change)
            # must not leave the reviewer with a dead tap and no way to act.
            logger.warning(
                "manual_payment.proof_photo_failed", payment_id=payment.id, error=str(exc)
            )
    await show(query, caption, keyboard, force_new=True)


@router.callback_query(ManualCB.filter(F.action == "resend"))
async def resend_review(query: CallbackQuery, callback_data: ManualCB, **data):
    """Re-attempt the channel post for a request whose notification never landed.

    Resend has no financial effect -- same payment, no new row, no wallet
    change, no status/UTR change -- so it only needs the weaker "payments"
    permission, not the "balance" permission Approve/Decline require.
    """
    context = build_context(data)
    require(context.admin_role, "payments")
    manual = _service(context)

    payment = await manual.get(callback_data.payment_id)
    if payment is None:
        await toast(query, context.text("errors.order_not_found"), alert=True)
        return
    if payment.status != PaymentStatus.PENDING:
        await toast(query, context.text("wallet.manual_already_reviewed"), alert=True)
        return

    sent = await post_for_review(query.bot, context, manual, payment, data["notifications"])
    await toast(
        query,
        context.text("wallet.manual_resend_done" if sent else "wallet.manual_resend_failed"),
        alert=not sent,
    )
    await open_request(query, callback_data, **data)


@router.callback_query(ManualCB.filter(F.action == "approve_confirm"))
async def confirm_approve(query: CallbackQuery, callback_data: ManualCB, **data):
    """Approve is the one tap here that moves real money -- confirm first.

    Only swaps the keyboard in place; the card's own text/photo is untouched,
    so cancelling can restore it exactly without re-fetching or re-sending
    anything.
    """
    context = build_context(data)
    manual = _service(context)
    if not manual.can_review(query.from_user.id):
        raise AccessDeniedError("not a payment reviewer")

    payment = await manual.get(callback_data.payment_id)
    if payment is None:
        await toast(query, context.text("errors.order_not_found"), alert=True)
        return
    if payment.status != PaymentStatus.PENDING:
        await toast(query, context.text("wallet.manual_already_reviewed"), alert=True)
        return

    await query.answer()
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Yes, Approve",
            callback_data=ManualCB(action="approve", payment_id=payment.id).pack(),
            style=SUCCESS,
        ),
        InlineKeyboardButton(
            text="❌ Cancel",
            callback_data=ManualCB(action="approve_cancel", payment_id=payment.id).pack(),
        ),
    )
    if query.message is not None:
        await query.message.edit_reply_markup(reply_markup=builder.as_markup())


@router.callback_query(ManualCB.filter(F.action == "approve_cancel"))
async def cancel_approve(query: CallbackQuery, callback_data: ManualCB, **data):
    context = build_context(data)
    manual = _service(context)
    if not manual.can_review(query.from_user.id):
        raise AccessDeniedError("not a payment reviewer")

    payment = await manual.get(callback_data.payment_id)
    if payment is None:
        await toast(query, context.text("errors.order_not_found"), alert=True)
        return

    await query.answer()
    if query.message is not None:
        missing_notification = payment.review_message_id is None
        await query.message.edit_reply_markup(
            reply_markup=decision_keyboard(context.texts, payment.id, missing_notification)
        )


@router.callback_query(ManualCB.filter(F.action == "approve"))
async def approve(query: CallbackQuery, callback_data: ManualCB, **data):
    context = build_context(data)
    manual = _service(context)

    decision = await manual.approve(callback_data.payment_id, query.from_user.id)
    if not decision.applied:
        await toast(query, context.text("wallet.manual_already_reviewed"), alert=True)
        await _close_review(query, context, decision, reviewer=query.from_user)
        return

    await query.answer()
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
        context.text("wallet.manual_decline_done", request_id=payment_id, reason=reason),
        reply_parameters=build_reply_parameters(message),
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
    """Strip the buttons and record the outcome as a reply.

    A reply works whether the card was a photo (caption) or the text-only
    fallback -- editing the caption directly does not: ``edit_caption`` is
    rejected outright on a plain text message, which used to leave the
    text-only fallback's outcome never recorded on screen.
    """
    verdict = context.text(
        "wallet.manual_verdict_approved" if decision.approved else "wallet.manual_verdict_declined",
        reviewer=f"@{reviewer.username}" if reviewer.username else str(reviewer.id),
        request_id=decision.payment.id,
    )
    if query.message is None:
        return
    # Independent try/except per call: a decision is already committed to the
    # database by this point, so one call failing must not swallow the other
    # -- stripping the buttons still matters even if the reply fails, and the
    # reply still matters even if the buttons could not be stripped. Either
    # failure is logged visibly: the outcome is decided either way, so a
    # missing on-screen record is an audit-trail gap, not routine noise.
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError as exc:
        logger.warning(
            "manual_payment.markup_strip_failed", payment_id=decision.payment.id, error=str(exc)
        )
    try:
        await query.message.reply(verdict)
    except TelegramAPIError as exc:
        logger.warning(
            "manual_payment.verdict_reply_failed", payment_id=decision.payment.id, error=str(exc)
        )


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
