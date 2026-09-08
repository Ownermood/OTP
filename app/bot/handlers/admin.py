"""Admin panel.

Access is decided by :func:`app.services.admin.can` against the role configured
in ``ADMIN_IDS``/``ADMIN_ROLES`` -- never by anything in callback data. Every
mutating action writes an audit row.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import AdminCB, Nav
from app.bot.handlers.common import Context, build_context, show, toast
from app.bot.states import AdminStates
from app.core.constants import AdminRole, OrderStatus
from app.core.exceptions import AccessDeniedError, ValidationError
from app.core.logging import get_logger
from app.core.money import format_money, parse_amount
from app.services.admin import can
from app.utils.formatting import format_datetime, order_icon
from app.utils.validators import parse_positive_int, parse_promo_code

router = Router(name="admin")
logger = get_logger(__name__)

PERIODS = {"1": ("Today", 1), "7": ("7 days", 7), "30": ("30 days", 30)}

AUDIENCES = {
    "all": "All users",
    "active": "Active (7d)",
    "paying": "Paying users",
    "with_orders": "Users with orders",
}


def _guard(context: Context, permission: str) -> AdminRole:
    """Resolve and check the caller's role, raising if they lack the permission."""
    role = context.admin_role
    if not can(role, permission):
        raise AccessDeniedError(f"missing permission: {permission}")
    return role


@router.message(Command("admin"))
async def open_panel(message: Message, state: FSMContext, **data):
    context = build_context(data)
    role = _guard(context, "dashboard")
    await state.clear()
    await show(message, context.text("admin.panel", role=role.value.title()), _panel_keyboard(role))


@router.callback_query(AdminCB.filter(F.action == "panel"))
async def back_to_panel(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    role = _guard(context, "dashboard")
    await state.clear()
    await show(query, context.text("admin.panel", role=role.value.title()), _panel_keyboard(role))


# -- dashboard --------------------------------------------------------------


@router.callback_query(AdminCB.filter(F.action == "dashboard"))
async def dashboard(query: CallbackQuery, callback_data: AdminCB, **data):
    context = build_context(data)
    _guard(context, "dashboard")

    label, days = PERIODS.get(callback_data.value or "1", PERIODS["1"])
    board = await context.admin.dashboard(days)
    currency = context.settings.currency_symbol

    builder = InlineKeyboardBuilder()
    builder.row(
        *[
            InlineKeyboardButton(
                text=name, callback_data=AdminCB(action="dashboard", value=key).pack()
            )
            for key, (name, _) in PERIODS.items()
        ]
    )
    builder.row(
        InlineKeyboardButton(text="📡 Status", callback_data=AdminCB(action="health").pack())
    )
    builder.row(_back_button())

    await show(
        query,
        context.text(
            "admin.dashboard",
            period=label,
            users_total=board.users_total,
            users_new=board.users_new,
            users_active=board.users_active,
            orders=board.orders,
            orders_success=board.orders_success,
            orders_failed=board.orders_failed,
            conversion=f"{board.conversion:.1f}",
            revenue=format_money(board.revenue, currency),
            deposits=format_money(board.deposits, currency),
            refunds=format_money(board.refunds, currency),
            average_order=format_money(board.average_order, currency),
            top_services=", ".join(f"{n} ({c})" for n, c in board.top_services) or "—",
            top_countries=", ".join(f"{n} ({c})" for n, c in board.top_countries) or "—",
        ),
        builder.as_markup(),
    )


@router.callback_query(AdminCB.filter(F.action == "health"))
async def health(query: CallbackQuery, **data):
    """Live provider/database status, probed on demand."""
    context = build_context(data)
    _guard(context, "dashboard")

    sms_provider = data["sms_provider"]
    sms_ok = await sms_provider.health_check()
    provider_balance = 0
    if sms_ok:
        try:
            provider_balance = await sms_provider.get_balance()
        except Exception:
            sms_ok = False

    payment_ok = all(
        [await provider.health_check() for provider in data["payment_providers"].values()]
    )
    smm_provider = data["smm_provider"]
    smm_status = "⚪️ Disabled"
    if smm_provider is not None:
        smm_status = "🟢 Online" if await smm_provider.health_check() else "🔴 Offline"

    from app.database import check_connection

    db_ok = await check_connection(data["engine"])
    maintenance = await context.admin.is_maintenance(context.settings.maintenance_mode)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=("✅ Disable maintenance" if maintenance else "🔧 Enable maintenance"),
            callback_data=AdminCB(action="maintenance", value=str(not maintenance).lower()).pack(),
        )
    )
    builder.row(_back_button())

    await show(
        query,
        context.text(
            "admin.health",
            sms_status="🟢 Online" if sms_ok else "🔴 Offline",
            payment_status="🟢 Online" if payment_ok else "🔴 Offline",
            smm_status=smm_status,
            db_status="🟢 Healthy" if db_ok else "🔴 Unreachable",
            provider_balance=format_money(provider_balance, context.settings.currency_symbol),
            maintenance="ON" if maintenance else "OFF",
        ),
        builder.as_markup(),
    )


@router.callback_query(AdminCB.filter(F.action == "maintenance"))
async def toggle_maintenance(query: CallbackQuery, callback_data: AdminCB, **data):
    context = build_context(data)
    role = _guard(context, "maintenance")
    enabled = callback_data.value == "true"
    await context.admin.set_maintenance(query.from_user.id, role, enabled)
    await toast(query, context.text("admin.maintenance_on" if enabled else "admin.maintenance_off"))
    await health(query, **data)


# -- search -----------------------------------------------------------------


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
            )
        )
    if can(role, "ban"):
        builder.row(
            InlineKeyboardButton(
                text=("✅ Unban" if user.is_banned else "🚫 Ban"),
                callback_data=AdminCB(
                    action="unban" if user.is_banned else "ban", value=str(user.id)
                ).pack(),
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


@router.callback_query(AdminCB.filter(F.action == "promo"))
async def promo_list(query: CallbackQuery, **data):
    context = build_context(data)
    _guard(context, "promo")

    promos = await context.promo.list_all()
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Create", callback_data=AdminCB(action="promo_new").pack())
    )
    builder.row(_back_button())

    lines = [
        f"🎟 <code>{p.code}</code> — "
        + (
            f"{p.percent}% of deposit"
            if p.percent
            else format_money(p.amount, context.settings.currency_symbol)
        )
        + f" · {p.used_count}/{p.max_activations} used"
        for p in promos[:15]
    ]
    body = "\n".join(lines) or context.text("common.empty")
    await show(
        query,
        context.text("admin.promo_list", count=len(promos)) + "\n\n" + body,
        builder.as_markup(),
    )


@router.callback_query(AdminCB.filter(F.action == "promo_new"))
async def promo_new(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    _guard(context, "promo")
    await state.set_state(AdminStates.promo_code)
    await show(query, context.text("admin.promo_create_code"), _back_only())


@router.message(AdminStates.promo_code)
async def promo_code(message: Message, state: FSMContext, **data):
    context = build_context(data)
    _guard(context, "promo")
    code = parse_promo_code(message.text or "")
    await state.set_state(AdminStates.promo_amount)
    await state.update_data(promo_code=code)
    await show(message, context.text("admin.promo_create_amount", code=code), _back_only())


@router.message(AdminStates.promo_amount)
async def promo_amount(message: Message, state: FSMContext, **data):
    """Accept either a flat bonus (``50``) or a deposit percentage (``10%``)."""
    context = build_context(data)
    _guard(context, "promo")

    raw = (message.text or "").strip()
    if raw.endswith("%"):
        percent = parse_positive_int(raw.rstrip("%"), minimum=1, maximum=100)
        amount, label = 0, f"{percent}% of next deposit"
    else:
        percent = 0
        amount = parse_amount(raw)
        if amount is None:
            raise ValidationError("unparseable amount")
        label = format_money(amount, context.settings.currency_symbol)

    stored = await state.get_data()
    await state.set_state(AdminStates.promo_limit)
    await state.update_data(promo_amount=amount, promo_percent=percent)
    await show(
        message,
        context.text("admin.promo_create_limit", code=stored["promo_code"], amount=label),
        _back_only(),
    )


@router.message(AdminStates.promo_limit)
async def promo_limit(message: Message, state: FSMContext, **data):
    context = build_context(data)
    role = _guard(context, "promo")
    limit = parse_positive_int(message.text or "", minimum=1, maximum=1_000_000)

    stored = await state.get_data()
    await state.clear()
    percent = int(stored.get("promo_percent", 0))
    promo = await context.promo.create(
        code=stored["promo_code"],
        amount=int(stored["promo_amount"]),
        percent=percent,
        max_activations=limit,
        expires_at=None,
        min_deposit=0,
        created_by=message.from_user.id,
    )
    await context.admin.log(message.from_user.id, role, "promo_create", promo.code)
    await show(
        message,
        context.text(
            "admin.promo_created",
            code=promo.code,
            amount=(
                f"{promo.percent}% of next deposit"
                if promo.percent
                else format_money(promo.amount, context.settings.currency_symbol)
            ),
            limit=promo.max_activations,
        ),
        _back_only(),
    )


# -- broadcast --------------------------------------------------------------


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
async def broadcast_send(message: Message, state: FSMContext, **data):
    """Send immediately. The notification service handles Telegram's rate limits."""
    context = build_context(data)
    role = _guard(context, "broadcast")

    stored = await state.get_data()
    await state.clear()
    recipients = [int(user_id) for user_id in stored.get("recipients", [])]

    delivered, failed = await data["notifications"].broadcast(recipients, message.html_text)
    await context.admin.log(
        message.from_user.id, role, "broadcast", stored.get("audience"), f"{delivered} delivered"
    )
    await show(
        message,
        context.text("admin.broadcast_done", delivered=delivered, failed=failed),
        _back_only(),
    )


# -- audit ------------------------------------------------------------------


@router.callback_query(AdminCB.filter(F.action == "logs"))
async def audit_log(query: CallbackQuery, **data):
    context = build_context(data)
    _guard(context, "logs")

    actions = await context.admin.audit_log()
    lines = [
        f"🧾 <b>{a.action}</b> by <code>{a.admin_id}</code>"
        + (f" → <code>{a.target}</code>" if a.target else "")
        + (f"\n<i>{a.details}</i>" if a.details else "")
        + f"\n<i>{format_datetime(a.created_at)}</i>"
        for a in actions
    ]
    builder = InlineKeyboardBuilder()
    builder.row(_back_button())
    body = "\n\n".join(lines) or context.text("common.empty")
    await show(
        query, context.text("admin.audit", count=len(actions)) + "\n\n" + body, builder.as_markup()
    )


# -- keyboards --------------------------------------------------------------


def _panel_keyboard(role: AdminRole):
    """Only show sections the role can actually open."""
    builder = InlineKeyboardBuilder()
    sections = [
        ("dashboard", "📊 Dashboard", "dashboard"),
        ("users", "👥 Users", "search"),
        ("orders", "📦 Orders", "orders"),
        ("payments", "💳 Payments", "payments"),
        ("promo", "🎟 Promo Codes", "promo"),
        ("broadcast", "📢 Broadcast", "broadcast"),
        ("logs", "🧾 Audit Log", "logs"),
    ]
    row: list[InlineKeyboardButton] = []
    for permission, label, action in sections:
        if not can(role, permission):
            continue
        row.append(InlineKeyboardButton(text=label, callback_data=AdminCB(action=action).pack()))
        if len(row) == 2:
            builder.row(*row)
            row = []
    if row:
        builder.row(*row)
    builder.row(
        InlineKeyboardButton(text="🏠 Main Menu", callback_data=Nav(to="home").pack())
    )
    return builder.as_markup()


def _back_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="🔙 Back", callback_data=AdminCB(action="panel").pack())


def _back_only():
    builder = InlineKeyboardBuilder()
    builder.row(_back_button())
    return builder.as_markup()
