"""Manual deposits: the reviewer's side.

Approve and Decline are tapped from the review channel. Whether the tapper may
decide anything is resolved from the configured admin roles on every tap --
the buttons are visible to everyone who can see the channel.
"""

from __future__ import annotations

from types import SimpleNamespace

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
        await _record_verdict(query.bot, context, decision, query.from_user, tapped_from=query.message)
        return

    await query.answer()
    await _record_verdict(query.bot, context, decision, query.from_user, tapped_from=query.message)
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
    """Ask for a reason, so the user is told something useful.

    The message Decline was tapped from -- the channel card, or the admin
    panel's copy of it -- is stashed now, because it is only reachable here;
    by the time the reason comes back as a DM this is a fresh update with no
    such message of its own.
    """
    context = build_context(data)
    manual = _service(context)
    if not manual.can_review(query.from_user.id):
        raise AccessDeniedError("not a payment reviewer")

    await state.set_state(ManualPaymentStates.declining)
    await state.update_data(
        decline_payment_id=callback_data.payment_id,
        decline_source_chat_id=query.message.chat.id if query.message else None,
        decline_source_message_id=query.message.message_id if query.message else None,
    )
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
    source_chat_id = stored.get("decline_source_chat_id")
    source_message_id = stored.get("decline_source_message_id")

    decision = await manual.decline(payment_id, message.from_user.id, reason)
    if not decision.applied:
        await message.answer(context.text("wallet.manual_already_reviewed"))
        return

    tapped_from = (
        SimpleNamespace(
            chat=SimpleNamespace(id=source_chat_id), message_id=source_message_id
        )
        if source_chat_id is not None
        else None
    )
    await _record_verdict(message.bot, context, decision, message.from_user, tapped_from=tapped_from)
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


async def _record_verdict(bot, context: Context, decision, reviewer, *, tapped_from=None) -> None:
    """Close the decision out everywhere it might still be showing.

    The channel copy is the authoritative record and is always targeted
    directly by ``payment.review_message_id`` -- regardless of whether the
    decision was actually made by tapping the channel post, by tapping its
    copy in the admin panel, or by replying to a DM decline prompt. Approving
    from the panel used to strip/reply only on the panel's own message,
    leaving the channel post stuck showing live Approve/Decline buttons on an
    already-settled payment -- reviewers glancing at the channel had no way
    to tell it was already handled.

    ``tapped_from`` is whatever message the admin actually interacted with;
    if that differs from the channel post (the panel case) it gets the same
    treatment too, purely as a convenience -- the channel update above is
    what actually matters.
    """
    verdict = context.text(
        "wallet.manual_verdict_approved" if decision.approved else "wallet.manual_verdict_declined",
        reviewer=f"@{reviewer.username}" if reviewer.username else str(reviewer.id),
        request_id=decision.payment.id,
    )
    payment = decision.payment

    targets: list[tuple[int, int]] = []
    if payment.review_message_id:
        targets.append((context.settings.manual_payment_channel_id, payment.review_message_id))
    if tapped_from is not None:
        candidate = (tapped_from.chat.id, tapped_from.message_id)
        if candidate not in targets:
            targets.append(candidate)

    # Independent try/except per call and per target: the decision is already
    # committed to the database by this point, so one failure must not
    # swallow another -- every surface gets its own attempt, and a failure on
    # one is logged without blocking the rest.
    for chat_id, message_id in targets:
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )
        except TelegramAPIError as exc:
            logger.warning(
                "manual_payment.markup_strip_failed",
                payment_id=payment.id,
                chat_id=chat_id,
                error=str(exc),
            )
        try:
            await bot.send_message(chat_id=chat_id, text=verdict, reply_to_message_id=message_id)
        except TelegramAPIError as exc:
            logger.warning(
                "manual_payment.verdict_reply_failed",
                payment_id=payment.id,
                chat_id=chat_id,
                error=str(exc),
            )
