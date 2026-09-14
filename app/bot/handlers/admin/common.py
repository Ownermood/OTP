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


async def _panel_keyboard(context: Context, role: AdminRole, user_id: int):
    """The dashboard's top level: broad categories only -- Payments, Promo,
    Payment QR, pricing, broadcast, backup and the audit log all now live one
    tap deeper in Finance/Operations, so this stays a handful of buttons
    instead of a nine-item wall. Permissions gets its own entry (not nested
    under Users) since managing *other admins* is a different kind of action
    from managing regular users."""
    pending_badge = ""
    if can(role, "payments"):
        pending_badge = f" ({await context.admin.pending_payment_count()})"

    texts = context.texts
    builder = InlineKeyboardBuilder()

    sections: list[tuple[str, str, str | None]] = []
    if can(role, "dashboard"):
        sections.append(("Dashboard", "dashboard", "statistics"))
    if can(role, "users"):
        sections.append(("Users", "search", "account"))
    if can(role, "orders"):
        sections.append(("Orders", "orders", "orders"))
    if can(role, "payments") or can(role, "promo") or can(role, "settings"):
        sections.append((f"Finance{pending_badge}", "menu_finance", "payment"))
    if role is AdminRole.OWNER:
        sections.append(("Permissions", "permissions", "admin"))
    if can(role, "broadcast") or can(role, "backup") or can(role, "logs"):
        sections.append(("🛠 Operations", "menu_ops", None))

    row: list[InlineKeyboardButton] = []
    for label, action, icon_role in sections:
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
            text="Refresh",
            icon_custom_emoji_id=texts.icon("refresh"),
            # page=2: reaching the panel (from Home's Admin Panel button, or
            # any section's Back button) also packs action="panel" -- without
            # a distinct payload here, an immediate Refresh tap collides with
            # that same string and ThrottleMiddleware silently drops it as a
            # duplicate press.
            callback_data=AdminCB(action="panel", page=2).pack(),
        ),
        InlineKeyboardButton(
            text="Main Menu", icon_custom_emoji_id=texts.icon("home"), callback_data=Nav(to="home").pack()
        ),
    )
    return builder.as_markup()


async def _menu_finance_keyboard(context: Context, role: AdminRole, user_id: int):
    """Payments, Promo, Payment QR and (for TG-Lion) price overrides --
    everything about money in one place."""
    pending_badge = ""
    if can(role, "payments"):
        pending_badge = f" ({await context.admin.pending_payment_count()})"

    texts = context.texts
    builder = InlineKeyboardBuilder()
    if can(role, "payments"):
        builder.row(
            InlineKeyboardButton(
                text=f"Payments{pending_badge}",
                icon_custom_emoji_id=texts.icon("payment"),
                callback_data=AdminCB(action="payments").pack(),
                style=PRIMARY,
            ),
            InlineKeyboardButton(
                text="Pending Deposits",
                icon_custom_emoji_id=texts.icon("pending"),
                callback_data=AdminCB(action="pending").pack(),
                style=PRIMARY,
            ),
        )
    row: list[InlineKeyboardButton] = []
    if can(role, "promo"):
        row.append(
            InlineKeyboardButton(
                text="🎟 Promo Codes",
                callback_data=AdminCB(action="promo").pack(),
                style=PRIMARY,
            )
        )
    if can(role, "settings"):
        row.append(
            InlineKeyboardButton(
                text="📲 Payment QR",
                callback_data=AdminCB(action="qr").pack(),
                style=PRIMARY,
            )
        )
    if row:
        builder.row(*row)
    builder.row(
        _back_button(),
        InlineKeyboardButton(
            text="Refresh",
            icon_custom_emoji_id=texts.icon("refresh"),
            # page=2 (unused by the handler) just to make this packed string
            # differ from the "Finance" button that opened this screen --
            # otherwise ThrottleMiddleware's duplicate-callback suppression
            # treats an immediate Refresh tap as a repeat of that same press
            # and silently drops it.
            callback_data=AdminCB(action="menu_finance", page=2).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="Main Menu", icon_custom_emoji_id=texts.icon("home"), callback_data=Nav(to="home").pack()
        )
    )
    return builder.as_markup()


async def _menu_ops_keyboard(context: Context, role: AdminRole):
    """Broadcast, Backup and the audit log -- the operational, not
    money-touching, side of running the bot."""
    texts = context.texts
    builder = InlineKeyboardBuilder()
    if can(role, "broadcast"):
        builder.row(
            InlineKeyboardButton(
                text="📢 Broadcast",
                callback_data=AdminCB(action="broadcast").pack(),
                style=PRIMARY,
            )
        )
    if can(role, "backup"):
        builder.row(
            InlineKeyboardButton(
                text="💾 Backup",
                callback_data=AdminCB(action="backup").pack(),
                style=PRIMARY,
            )
        )
    if can(role, "logs"):
        builder.row(
            InlineKeyboardButton(
                text="🧾 Audit Log",
                callback_data=AdminCB(action="logs").pack(),
                style=PRIMARY,
            )
        )
    builder.row(
        _back_button(),
        InlineKeyboardButton(
            text="Refresh",
            icon_custom_emoji_id=texts.icon("refresh"),
            # page=2: see the matching comment in _menu_finance_keyboard.
            callback_data=AdminCB(action="menu_ops", page=2).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="Main Menu", icon_custom_emoji_id=texts.icon("home"), callback_data=Nav(to="home").pack()
        )
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
    keyboard = await _panel_keyboard(context, role, message.from_user.id)
    await show(message, context.text("admin.panel", role=role.value.title()), keyboard)


@router.callback_query(AdminCB.filter(F.action == "panel"))
async def back_to_panel(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    role = _guard(context, "dashboard")
    await state.clear()
    keyboard = await _panel_keyboard(context, role, query.from_user.id)
    await show(query, context.text("admin.panel", role=role.value.title()), keyboard)


@router.callback_query(AdminCB.filter(F.action == "menu_finance"))
async def open_finance_menu(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    role = _guard(context, "dashboard")
    await state.clear()
    keyboard = await _menu_finance_keyboard(context, role, query.from_user.id)
    await show(query, context.text("admin.menu_finance"), keyboard)


@router.callback_query(AdminCB.filter(F.action == "menu_ops"))
async def open_ops_menu(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    role = _guard(context, "dashboard")
    await state.clear()
    keyboard = await _menu_ops_keyboard(context, role)
    await show(query, context.text("admin.menu_ops"), keyboard)


# -- dashboard --------------------------------------------------------------
