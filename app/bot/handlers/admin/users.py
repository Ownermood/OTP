"""User search, detail, audited balance adjustments and bans."""

from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import AdminCB
from app.bot.handlers.admin.common import _back_button, _back_only, _guard, router
from app.bot.handlers.common import build_context, show, toast
from app.bot.keyboards.style import DANGER, PRIMARY, SUCCESS
from app.bot.states import AdminStates
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.core.money import format_money, parse_amount
from app.services.admin import can
from app.utils.formatting import format_datetime, order_icon

logger = get_logger(__name__)

@router.callback_query(AdminCB.filter(F.action == "search"))
async def prompt_search(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    _guard(context, "users")
    await state.set_state(AdminStates.searching)
    await show(query, context.text("admin.search_prompt"), _back_only())


@router.message(AdminStates.searching)
async def do_search(message: Message, state: FSMContext, **data):
    """One box searches users, orders and payments -- whichever matches."""
    context = build_context(data)
    _guard(context, "users")
    await state.clear()

    term = (message.text or "").strip()
    users = await context.admin.search_users(term)
    orders = await context.admin.search_orders(term)
    payments = await context.admin.search_payments(term)

    if not (users or orders or payments):
        await show(message, context.text("admin.no_results"), _back_only())
        return

    builder = InlineKeyboardBuilder()
    for user in users[:5]:
        builder.row(
            InlineKeyboardButton(
                text=f"👤 {user.username or user.id}",
                callback_data=AdminCB(action="user", value=str(user.id)).pack(),
            )
        )
    lines = []
    for order in orders[:5]:
        lines.append(
            f"{order_icon(order.status)} <b>#{order.id}</b> {order.service_name} — "
            f"{format_money(order.price, context.settings.currency_symbol)} "
            f"(user <code>{order.user_id}</code>, provider <code>{order.provider_order_id}</code>)"
        )
    for payment in payments[:5]:
        lines.append(
            f"💳 <b>#{payment.id}</b> {payment.status} — "
            f"{format_money(payment.amount, context.settings.currency_symbol)} "
            f"(user <code>{payment.user_id}</code>)"
        )
    builder.row(_back_button())

    body = "\n\n".join(lines) if lines else "Select a user below."
    await show(message, f"🔍 <b>RESULTS</b>\n\n{body}", builder.as_markup())


@router.callback_query(AdminCB.filter(F.action == "user"))
async def user_detail(query: CallbackQuery, callback_data: AdminCB, **data):
    context = build_context(data)
    role = _guard(context, "users")

    detail = await context.admin.user_detail(int(callback_data.value))
    if detail is None:
        await toast(query, context.text("admin.no_results"), alert=True)
        return
    user, orders = detail

    builder = InlineKeyboardBuilder()
    if can(role, "balance"):
        builder.row(
            InlineKeyboardButton(
                text="💰 Adjust balance",
                callback_data=AdminCB(action="balance", value=str(user.id)).pack(),
                style=PRIMARY,
            )
        )
    if can(role, "ban"):
        builder.row(
            InlineKeyboardButton(
                text=("✅ Unban" if user.is_banned else "🚫 Ban"),
                callback_data=AdminCB(
                    action="unban" if user.is_banned else "ban", value=str(user.id)
                ).pack(),
                style=SUCCESS if user.is_banned else DANGER,
            )
        )
    builder.row(_back_button())

    await show(
        query,
        context.text(
            "admin.user_detail",
            user_id=user.id,
            username=f"@{user.username}" if user.username else "—",
            balance=format_money(user.balance, context.settings.currency_symbol),
            orders=len(orders),
            spent=format_money(user.total_spent, context.settings.currency_symbol),
            referral_earned=format_money(user.referral_earned, context.settings.currency_symbol),
            joined=format_datetime(user.created_at),
            status="🚫 Banned" if user.is_banned else "🟢 Active",
        ),
        builder.as_markup(),
    )


# -- balance adjustment -----------------------------------------------------


@router.callback_query(AdminCB.filter(F.action == "balance"))
async def prompt_balance(query: CallbackQuery, callback_data: AdminCB, state: FSMContext, **data):
    context = build_context(data)
    _guard(context, "balance")

    detail = await context.admin.user_detail(int(callback_data.value))
    if detail is None:
        await toast(query, context.text("admin.no_results"), alert=True)
        return

    await state.set_state(AdminStates.entering_balance)
    await state.update_data(target_user=int(callback_data.value))
    await show(
        query,
        context.text(
            "admin.balance_prompt",
            user_id=callback_data.value,
            balance=format_money(detail[0].balance, context.settings.currency_symbol),
        ),
        _back_only(),
    )


@router.message(AdminStates.entering_balance)
async def enter_balance(message: Message, state: FSMContext, **data):
    context = build_context(data)
    _guard(context, "balance")

    raw = (message.text or "").strip()
    negative = raw.startswith("-")
    amount = parse_amount(raw.lstrip("+-"))
    if amount is None:
        raise ValidationError("unparseable amount")
    signed = -amount if negative else amount

    await state.set_state(AdminStates.entering_balance_reason)
    await state.update_data(amount=signed)
    await show(
        message,
        context.text(
            "admin.balance_reason",
            amount=format_money(signed, context.settings.currency_symbol),
        ),
        _back_only(),
    )


@router.message(AdminStates.entering_balance_reason)
async def apply_balance(message: Message, state: FSMContext, **data):
    """Apply the adjustment. Always audited, always a visible transaction."""
    context = build_context(data)
    role = _guard(context, "balance")

    stored = await state.get_data()
    await state.clear()
    user_id = int(stored["target_user"])
    amount = int(stored["amount"])
    reason = (message.text or "").strip()[:200] or "manual adjustment"

    balance = await context.admin.adjust_balance(
        message.from_user.id, role, user_id, amount, reason
    )
    await show(
        message,
        context.text(
            "admin.balance_done",
            user_id=user_id,
            amount=format_money(amount, context.settings.currency_symbol),
            balance=format_money(balance, context.settings.currency_symbol),
            reason=reason,
        ),
        _back_only(),
    )
    # An adjustment is not a payment: telling the user "PAYMENT RECEIVED" would
    # be wrong for a credit and nonsense for a deduction.
    await data["notifications"].notify_user(
        user_id,
        context.text(
            "wallet.admin_credit" if amount > 0 else "wallet.admin_debit",
            amount=format_money(abs(amount), context.settings.currency_symbol),
            balance=format_money(balance, context.settings.currency_symbol),
            reason=reason,
        ),
        essential=True,
    )


@router.callback_query(AdminCB.filter(F.action.in_({"ban", "unban"})))
async def toggle_ban(query: CallbackQuery, callback_data: AdminCB, **data):
    context = build_context(data)
    role = _guard(context, "ban")
    user_id = callback_data.value
    await context.admin.set_banned(
        query.from_user.id, role, int(user_id), callback_data.action == "ban"
    )
    await toast(query, context.text("common.done"))
    await user_detail(query, AdminCB(action="user", value=user_id), **data)


# -- orders / payments ------------------------------------------------------
