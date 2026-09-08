"""The payment QR: view it, replace it, remove it.

Uploading through the bot means the QR can be changed from a phone -- no server
access, no redeploy. The image is kept as a Telegram file id rather than a file,
so there is nothing to store or mount.

Owner-only. This decides where every user's money goes.
"""

from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import AdminCB
from app.bot.handlers.admin.common import _back_button, _back_only, _guard, router
from app.bot.handlers.common import build_context, show, toast
from app.bot.keyboards.style import DANGER, PRIMARY
from app.bot.states import AdminStates


@router.callback_query(AdminCB.filter(F.action == "qr"))
async def show_qr(query: CallbackQuery, state: FSMContext, **data):
    """Show whichever QR users are currently being sent, and how to change it."""
    context = build_context(data)
    _guard(context, "settings")
    await state.clear()

    file_id = await context.admin.get_qr_file_id()
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=("🔄 Replace QR" if file_id else "📤 Upload QR"),
            callback_data=AdminCB(action="qr_upload").pack(),
            style=PRIMARY,
        )
    )
    if file_id:
        builder.row(
            InlineKeyboardButton(
                text="🗑 Remove QR",
                callback_data=AdminCB(action="qr_clear").pack(),
                style=DANGER,
            )
        )
    builder.row(_back_button())

    caption = context.text(
        "admin.qr_current" if file_id else "admin.qr_none",
        upi_id=context.settings.upi_id or "—",
        source=_source(context, file_id),
    )
    if file_id and query.message is not None:
        # Send rather than edit: the current screen may be a text message.
        await query.answer()
        await query.message.answer_photo(
            file_id, caption=caption, reply_markup=builder.as_markup()
        )
        return

    await show(query, caption, builder.as_markup())


@router.callback_query(AdminCB.filter(F.action == "qr_upload"))
async def prompt_upload(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    _guard(context, "settings")

    await state.set_state(AdminStates.uploading_qr)
    await show(query, context.text("admin.qr_upload"), _back_only(), force_new=True)


@router.message(AdminStates.uploading_qr, F.photo)
async def receive_qr(message: Message, state: FSMContext, **data):
    """Store the uploaded image as the payment QR."""
    context = build_context(data)
    role = _guard(context, "settings")

    file_id = message.photo[-1].file_id
    await state.clear()
    await context.admin.set_qr_file_id(message.from_user.id, role, file_id)

    await message.answer_photo(
        file_id,
        caption=context.text("admin.qr_saved", upi_id=context.settings.upi_id or "—"),
        reply_markup=_back_only(),
    )


@router.message(AdminStates.uploading_qr, F.document)
async def reject_document(message: Message, **data):
    """A QR sent as a file loses nothing, but Telegram cannot show it inline."""
    context = build_context(data)
    await message.answer(context.text("admin.qr_needs_photo"))


@router.message(AdminStates.uploading_qr)
async def reject_text(message: Message, **data):
    context = build_context(data)
    await message.answer(context.text("admin.qr_needs_photo"))


@router.callback_query(AdminCB.filter(F.action == "qr_clear"))
async def clear_qr(query: CallbackQuery, state: FSMContext, **data):
    """Remove the uploaded QR and fall back to whatever .env configures."""
    context = build_context(data)
    role = _guard(context, "settings")

    await context.admin.clear_qr_file_id(query.from_user.id, role)
    await toast(query, context.text("common.done"))
    await show_qr(query, state, **data)


def _source(context, file_id: str | None) -> str:
    """Name what users are actually being sent right now."""
    if file_id:
        return "uploaded here"
    if context.settings.qr_image_path is not None:
        return f"UPI_QR_IMAGE ({context.settings.upi_qr_image})"
    if context.settings.upi_id:
        return "generated per request, with the amount inside"
    return "nothing configured"
