"""Audience selection, preview and the confirmed send."""

from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import AdminCB
from app.bot.handlers.admin.common import (
    AUDIENCES,
    _back_button,
    _back_only,
    _guard,
    router,
)
from app.bot.handlers.common import build_context, show, toast
from app.bot.states import AdminStates
from app.bot.texts import Safe


@router.callback_query(AdminCB.filter(F.action == "broadcast"))
async def broadcast_audience(query: CallbackQuery, **data):
    context = build_context(data)
    _guard(context, "broadcast")

    builder = InlineKeyboardBuilder()
    for key, label in AUDIENCES.items():
        builder.row(
            InlineKeyboardButton(
                text=label, callback_data=AdminCB(action="broadcast_to", value=key).pack()
            )
        )
    builder.row(_back_button())
    await show(query, context.text("admin.broadcast_audience"), builder.as_markup())


@router.callback_query(AdminCB.filter(F.action == "broadcast_to"))
async def broadcast_prompt(query: CallbackQuery, callback_data: AdminCB, state: FSMContext, **data):
    context = build_context(data)
    _guard(context, "broadcast")

    recipients = await context.admin.broadcast_audience(callback_data.value)
    await state.set_state(AdminStates.broadcast_text)
    await state.update_data(audience=callback_data.value, recipients=list(recipients))
    await show(
        query,
        context.text(
            "admin.broadcast_text",
            audience=AUDIENCES.get(callback_data.value, callback_data.value),
            count=len(recipients),
        ),
        _back_only(),
    )


@router.message(AdminStates.broadcast_text)
async def broadcast_preview(message: Message, state: FSMContext, **data):
    """Show exactly what will go out, and to how many people, before it does.

    A broadcast cannot be recalled, so it is never sent straight off a typed
    message.
    """
    context = build_context(data)
    _guard(context, "broadcast")

    stored = await state.get_data()
    recipients = [int(user_id) for user_id in stored.get("recipients", [])]
    await state.update_data(broadcast_body=message.html_text)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"✅ Send to {len(recipients)}",
            callback_data=AdminCB(action="broadcast_send").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(text="❌ Cancel", callback_data=AdminCB(action="panel").pack())
    )
    await show(
        message,
        context.text(
            "admin.broadcast_confirm", count=len(recipients), preview=Safe(message.html_text)
        ),
        builder.as_markup(),
    )


@router.callback_query(AdminCB.filter(F.action == "broadcast_send"))
async def broadcast_send(query: CallbackQuery, state: FSMContext, **data):
    """Send the previewed broadcast. Rate limiting lives in the notifier."""
    context = build_context(data)
    role = _guard(context, "broadcast")

    stored = await state.get_data()
    await state.clear()
    recipients = [int(user_id) for user_id in stored.get("recipients", [])]
    body = stored.get("broadcast_body", "")
    if not body or not recipients:
        await toast(query, context.text("errors.expired_action"), alert=True)
        return

    delivered, failed = await data["notifications"].broadcast(recipients, body)
    await context.admin.log(
        query.from_user.id, role, "broadcast", stored.get("audience"), f"{delivered} delivered"
    )
    await show(
        query,
        context.text("admin.broadcast_done", delivered=delivered, failed=failed),
        _back_only(),
    )


# -- audit ------------------------------------------------------------------
