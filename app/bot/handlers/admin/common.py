"""The panel itself, plus the shared router, permission guard and keyboards.

The router lives here and every section registers on it, so the panel is one
router however many modules it spans.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import AdminCB, Nav
from app.bot.handlers.common import Context, build_context, show
from app.bot.keyboards.style import PRIMARY
from app.core.constants import AdminRole
from app.core.exceptions import AccessDeniedError
from app.core.logging import get_logger
from app.services.admin import can

router = Router(name="admin")
logger = get_logger(__name__)

#: Dashboard time windows, keyed by the value carried in the callback.
PERIODS = {"1": ("Today", 1), "7": ("7 days", 7), "30": ("30 days", 30)}

#: Broadcast audiences, resolved to user ids by the admin service.
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


async def _panel_keyboard(context: Context, role: AdminRole):
    """Only show sections the role can actually open."""
    pending_badge = ""
    if can(role, "payments"):
        pending_badge = f" ({await context.admin.pending_payment_count()})"

    texts = context.texts
    builder = InlineKeyboardBuilder()
    sections = [
        ("dashboard", "📊 Dashboard", "dashboard", "statistics"),
        ("users", "👥 Users", "search", "account"),
        ("orders", "📦 Orders", "orders", "orders"),
        ("payments", f"💳 Payments{pending_badge}", "payments", "payment"),
        ("promo", "🎟 Promo Codes", "promo", None),
        ("settings", "📲 Payment QR", "qr", None),
        ("backup", "💾 Backup", "backup", None),
        ("broadcast", "📢 Broadcast", "broadcast", None),
        ("logs", "🧾 Audit Log", "logs", None),
    ]
    row: list[InlineKeyboardButton] = []
    for permission, label, action, icon_role in sections:
        if not can(role, permission):
            continue
        row.append(
            InlineKeyboardButton(
                text=label,
                icon_custom_emoji_id=texts.icon(icon_role) if icon_role else None,
                callback_data=AdminCB(action=action).pack(),
                style=PRIMARY,
            )
        )
        if len(row) == 2:
            builder.row(*row)
            row = []
    if row:
        builder.row(*row)
    builder.row(
        InlineKeyboardButton(
            text="🔄 Refresh",
            icon_custom_emoji_id=texts.icon("refresh"),
            callback_data=AdminCB(action="panel").pack(),
        ),
        InlineKeyboardButton(
            text="🏠 Main Menu", icon_custom_emoji_id=texts.icon("home"), callback_data=Nav(to="home").pack()
        ),
    )
    return builder.as_markup()


def _back_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="🔙 Back", callback_data=AdminCB(action="panel").pack())


def _back_only():
    builder = InlineKeyboardBuilder()
    builder.row(_back_button())
    return builder.as_markup()


@router.message(Command("admin"))
async def open_panel(message: Message, state: FSMContext, **data):
    context = build_context(data)
    role = _guard(context, "dashboard")
    await state.clear()
    keyboard = await _panel_keyboard(context, role)
    await show(message, context.text("admin.panel", role=role.value.title()), keyboard)


@router.callback_query(AdminCB.filter(F.action == "panel"))
async def back_to_panel(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    role = _guard(context, "dashboard")
    await state.clear()
    keyboard = await _panel_keyboard(context, role)
    await show(query, context.text("admin.panel", role=role.value.title()), keyboard)


# -- dashboard --------------------------------------------------------------
