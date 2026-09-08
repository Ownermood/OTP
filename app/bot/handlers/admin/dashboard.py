"""Analytics, live provider health, maintenance mode and the audit log."""

from __future__ import annotations

from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import AdminCB
from app.bot.handlers.admin.common import (
    PERIODS,
    _back_button,
    _guard,
    router,
)
from app.bot.handlers.common import build_context, show, toast
from app.core.logging import get_logger
from app.core.money import format_money
from app.utils.formatting import format_datetime

logger = get_logger(__name__)

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
