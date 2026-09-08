"""Display helpers shared by handlers and keyboards."""

from __future__ import annotations

from datetime import datetime, timedelta
from html import escape

from app.core.constants import OrderStatus, PaymentStatus

#: Status -> emoji, so a status badge looks the same everywhere in the bot.
ORDER_STATUS_ICONS = {
    OrderStatus.PENDING: "⏳",
    OrderStatus.PROCESSING: "🔄",
    OrderStatus.SUCCESS: "✅",
    OrderStatus.FAILED: "❌",
    OrderStatus.CANCELLED: "🚫",
    OrderStatus.REFUNDED: "↩️",
    OrderStatus.EXPIRED: "⌛",
}

PAYMENT_STATUS_ICONS = {
    PaymentStatus.PENDING: "⏳",
    PaymentStatus.PAID: "✅",
    PaymentStatus.EXPIRED: "⌛",
    PaymentStatus.FAILED: "❌",
    PaymentStatus.REFUNDED: "↩️",
}

DIVIDER = "━━━━━━━━━━━━━━"


def order_icon(status: OrderStatus | str) -> str:
    return ORDER_STATUS_ICONS.get(OrderStatus(status), "•")


def payment_icon(status: PaymentStatus | str) -> str:
    return PAYMENT_STATUS_ICONS.get(PaymentStatus(status), "•")


def availability_icon(count: int | None) -> str:
    """🟢 plenty / 🟡 running low / 🔴 none / ⚪️ unknown."""
    if count is None:
        return "⚪️"
    if count <= 0:
        return "🔴"
    if count < 25:
        return "🟡"
    return "🟢"


def html_escape(value: object) -> str:
    """Escape untrusted text before it goes into an HTML-parsed message."""
    return escape(str(value), quote=False)


def format_datetime(value: datetime) -> str:
    return value.strftime("%d %b %Y, %H:%M")


def format_duration(hours: int) -> str:
    """``4`` -> ``4 hours``; ``72`` -> ``3 days``."""
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    days = hours // 24
    remainder = hours % 24
    text = f"{days} day{'s' if days != 1 else ''}"
    return f"{text} {remainder}h" if remainder else text


def format_countdown(deadline: datetime, now: datetime | None = None) -> str:
    """``mm:ss`` remaining until ``deadline``, floored at zero."""
    remaining = deadline - (now or datetime.utcnow())
    if remaining < timedelta(0):
        remaining = timedelta(0)
    total_seconds = int(remaining.total_seconds())
    return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
