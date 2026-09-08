"""Filtered order and payment listings."""

from __future__ import annotations

from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import AdminCB
from app.bot.handlers.admin.common import _back_button, _guard, router
from app.bot.handlers.common import build_context, show
from app.core.constants import OrderStatus
from app.core.money import format_money
from app.utils.formatting import order_icon


@router.callback_query(AdminCB.filter(F.action == "orders"))
async def list_orders(query: CallbackQuery, callback_data: AdminCB, **data):
    context = build_context(data)
    _guard(context, "orders")

    status = OrderStatus(callback_data.value) if callback_data.value else None
    orders = await context.admin.list_orders(status)

    builder = InlineKeyboardBuilder()
    row = [
        InlineKeyboardButton(text="All", callback_data=AdminCB(action="orders").pack())
    ]
    for state_name in (OrderStatus.SUCCESS, OrderStatus.FAILED, OrderStatus.REFUNDED):
        row.append(
            InlineKeyboardButton(
                text=state_name.value.title(),
                callback_data=AdminCB(action="orders", value=state_name.value).pack(),
            )
        )
    builder.row(*row[:2])
    builder.row(*row[2:])
    builder.row(_back_button())

    lines = [
        f"{order_icon(o.status)} <b>#{o.id}</b> {o.service_name} — "
        f"{format_money(o.price, context.settings.currency_symbol)} "
        f"(<code>{o.user_id}</code>)"
        for o in orders[:15]
    ]
    body = "\n".join(lines) or context.text("common.empty")
    await show(query, f"📦 <b>ORDERS</b>\n\n{body}", builder.as_markup())


@router.callback_query(AdminCB.filter(F.action == "payments"))
async def list_payments(query: CallbackQuery, **data):
    context = build_context(data)
    _guard(context, "payments")

    payments = await context.admin.list_payments()
    lines = [
        f"💳 <b>#{p.id}</b> {p.status} — "
        f"{format_money(p.amount, context.settings.currency_symbol)} "
        f"(<code>{p.user_id}</code>, {p.provider})"
        for p in payments[:15]
    ]
    builder = InlineKeyboardBuilder()
    builder.row(_back_button())
    body = "\n".join(lines) or context.text("common.empty")
    await show(query, f"💳 <b>PAYMENTS</b>\n\n{body}", builder.as_markup())


# -- promo ------------------------------------------------------------------
