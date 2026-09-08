"""Manual deposits: the user's side.

The user pays by UPI or bank transfer outside the bot, then submits the
amount, the transaction reference and a screenshot. The request goes to the
review channel, and the balance moves only when a reviewer approves it --
that half lives in :mod:`app.bot.handlers.manual_review`.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot import keyboards
from app.bot.callbacks import ManualCB, PaymentCB
from app.bot.handlers.common import Context, build_context, show, toast
from app.bot.states import ManualPaymentStates
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.core.money import parse_amount, to_major, to_minor
from app.services.manual_payments import PROVIDER, ManualPaymentService, normalise_utr
from app.utils.formatting import format_datetime, truncate
from app.utils.qr import build_upi_link, render_qr

router = Router(name="manual_payments")
logger = get_logger(__name__)


def _service(context: Context) -> ManualPaymentService:
    return ManualPaymentService(context.session, context.payments, context.settings)

@router.callback_query(PaymentCB.filter((F.action == "method") & (F.provider == PROVIDER)))
async def start_manual_deposit(query: CallbackQuery, state: FSMContext, **data):
    """Show the operator's payment details and ask for an amount."""
    context = build_context(data)
    manual = _service(context)
    if not manual.enabled:
        await toast(query, context.text("errors.invalid_input"), alert=True)
        return

    await state.set_state(ManualPaymentStates.entering_amount)
    await show(
        query,
        context.text(
            "wallet.manual_start",
            minimum=context.money(to_minor(context.settings.min_deposit)),
            maximum=context.money(to_minor(context.settings.max_deposit)),
        ),
        keyboards.back_home(context.texts, context.locale, back_to="wallet"),
    )


@router.message(ManualPaymentStates.entering_amount)
async def enter_amount(message: Message, state: FSMContext, **data):
    """Accept the amount, then hand over a QR that already contains it."""
    context = build_context(data)
    amount = parse_amount(message.text or "")
    if amount is None:
        raise ValidationError("unparseable amount")
    context.payments.validate_amount(amount)

    await state.set_state(ManualPaymentStates.entering_utr)
    await state.update_data(manual_amount=amount)
    await _send_payment_qr(message, context, amount)


async def _send_payment_qr(message: Message, context: Context, amount: int) -> None:
    """Send the QR for this exact amount, or the operator's static one."""
    settings = context.settings
    caption = context.text(
        "wallet.manual_qr",
        amount=context.money(amount),
        upi_id=settings.upi_id or "—",
        payee=settings.payee_name,
    )
    keyboard = keyboards.back_home(context.texts, context.locale, back_to="wallet")

    static_qr = settings.qr_image_path
    if settings.upi_id:
        # Generated: the amount travels inside the code, so the payer's app
        # opens pre-filled and cannot drift from what they told the bot.
        link = build_upi_link(
            settings.upi_id,
            settings.payee_name,
            to_major(amount),
            note=f"{settings.service_name} top-up",
        )
        photo = BufferedInputFile(render_qr(link), filename="upi-qr.png")
    elif static_qr is not None and static_qr.exists():
        photo = FSInputFile(static_qr)
        caption = context.text(
            "wallet.manual_qr_static", amount=context.money(amount), payee=settings.payee_name
        )
    else:
        # Configuration guarantees one of the two, but never leave the user
        # staring at nothing if that ever changes.
        logger.error("manual_payment.no_qr_configured")
        await show(
            message,
            context.text("wallet.manual_utr", amount=context.money(amount)),
            keyboard,
        )
        return

    await message.answer_photo(photo, caption=caption, reply_markup=keyboard)


@router.message(ManualPaymentStates.entering_utr)
async def enter_utr(message: Message, state: FSMContext, **data):
    context = build_context(data)
    utr = normalise_utr(message.text or "")

    await state.set_state(ManualPaymentStates.entering_proof)
    await state.update_data(manual_utr=utr)
    await show(
        message,
        context.text("wallet.manual_proof", utr=utr),
        keyboards.back_home(context.texts, context.locale, back_to="wallet"),
    )


@router.message(ManualPaymentStates.entering_proof, F.photo)
async def submit_request(message: Message, state: FSMContext, **data):
    """Record the request and post it for review."""
    context = build_context(data)
    manual = _service(context)

    stored = await state.get_data()
    amount = int(stored.get("manual_amount", 0))
    utr = str(stored.get("manual_utr", ""))
    if not amount or not utr:
        await state.clear()
        raise ValidationError("submission expired")

    # Highest resolution the user sent, so a reviewer can actually read it.
    file_id = message.photo[-1].file_id
    await state.clear()

    payment = await manual.submit(message.from_user.id, amount, utr, file_id)
    await _post_for_review(message, context, manual, payment, data["notifications"])

    await show(
        message,
        context.text(
            "wallet.manual_submitted",
            request_id=payment.id,
            amount=context.money(payment.amount),
            utr=utr,
        ),
        keyboards.back_home(context.texts, context.locale, back_to="wallet"),
    )


@router.message(ManualPaymentStates.entering_proof)
async def proof_must_be_a_photo(message: Message, **data):
    """A document or text here is a mistake worth naming, not a silent failure."""
    context = build_context(data)
    await message.answer(context.text("wallet.manual_proof_required"))


async def _post_for_review(
    message: Message, context: Context, manual: ManualPaymentService, payment, notifications
) -> None:
    """Send the screenshot and details to the review channel."""
    user = message.from_user
    caption = context.text(
        "wallet.manual_review",
        request_id=payment.id,
        amount=context.money(payment.amount),
        utr=payment.invoice_id,
        user_id=user.id,
        username=f"@{user.username}" if user.username else "—",
        name=truncate(user.full_name or "—", 40),
        balance=context.money(context.user.balance),
        submitted_at=format_datetime(payment.created_at),
    )
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Approve",
            callback_data=ManualCB(action="approve", payment_id=payment.id).pack(),
        ),
        InlineKeyboardButton(
            text="❌ Decline",
            callback_data=ManualCB(action="decline", payment_id=payment.id).pack(),
        ),
    )

    try:
        posted = await message.bot.send_photo(
            chat_id=context.settings.manual_payment_channel_id,
            photo=payment.proof_file_id,
            caption=caption,
            reply_markup=builder.as_markup(),
        )
        await manual.set_review_message(payment, posted.message_id)
    except TelegramAPIError as exc:
        # The request is saved either way, so it is never lost -- but a channel
        # nobody can post to means nobody is reviewing, which admins must hear
        # about directly.
        logger.error(
            "manual_payment.review_post_failed",
            payment_id=payment.id,
            channel=context.settings.manual_payment_channel_id,
            error=str(exc),
        )
        await notifications.notify_admins(
            context.text("wallet.manual_post_failed", request_id=payment.id, error=str(exc)[:120])
        )


# -- review -----------------------------------------------------------------
