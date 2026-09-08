"""Shared enums and constants.

Statuses live here as enums so no handler ever compares against a bare string.
"""

from __future__ import annotations

from enum import StrEnum


class OrderStatus(StrEnum):
    """Lifecycle of an SMS activation or rental order."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    EXPIRED = "expired"

    @property
    def is_final(self) -> bool:
        return self not in (OrderStatus.PENDING, OrderStatus.PROCESSING)


class PaymentStatus(StrEnum):
    """Lifecycle of a deposit invoice."""

    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"
    FAILED = "failed"
    REFUNDED = "refunded"


class TransactionType(StrEnum):
    """Every balance movement is one of these, and every one is recorded."""

    DEPOSIT = "deposit"
    PURCHASE = "purchase"
    REFUND = "refund"
    REFERRAL = "referral"
    PROMO = "promo"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    ADMIN_ADJUSTMENT = "admin_adjustment"


class OrderKind(StrEnum):
    """What kind of product an order represents."""

    ACTIVATION = "activation"
    RENTAL = "rental"
    SMM = "smm"


class AdminRole(StrEnum):
    """Admin roles, ordered from most to least privileged."""

    OWNER = "owner"
    ADMIN = "admin"
    FINANCE = "finance"
    SUPPORT = "support"
    VIEWER = "viewer"


#: Which roles may perform which action. Checked server-side, never from callback data.
ROLE_PERMISSIONS: dict[AdminRole, frozenset[str]] = {
    AdminRole.OWNER: frozenset(
        {
            "dashboard", "users", "orders", "payments", "provider", "promo",
            "referrals", "broadcast", "settings", "logs", "balance", "ban",
            "maintenance", "backup",
        }
    ),
    AdminRole.ADMIN: frozenset(
        {
            "dashboard", "users", "orders", "payments", "provider", "promo",
            "referrals", "broadcast", "logs", "balance", "ban", "maintenance",
        }
    ),
    AdminRole.FINANCE: frozenset({"dashboard", "users", "payments", "orders", "balance", "logs"}),
    AdminRole.SUPPORT: frozenset({"dashboard", "users", "orders", "payments"}),
    AdminRole.VIEWER: frozenset({"dashboard", "orders", "payments"}),
}


class SmmCategory(StrEnum):
    """Platform buckets shown in the SMM panel menu."""

    INSTAGRAM = "instagram"
    TELEGRAM = "telegram"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    FACEBOOK = "facebook"
    TWITTER = "twitter"
    OTHER = "other"


#: Keywords used to bucket a provider's free-text service category into SmmCategory.
SMM_CATEGORY_KEYWORDS: dict[SmmCategory, tuple[str, ...]] = {
    SmmCategory.INSTAGRAM: ("instagram", "insta", "ig "),
    SmmCategory.TELEGRAM: ("telegram", "tg "),
    SmmCategory.YOUTUBE: ("youtube", "yt "),
    SmmCategory.TIKTOK: ("tiktok", "tik tok"),
    SmmCategory.FACEBOOK: ("facebook", "fb "),
    SmmCategory.TWITTER: ("twitter", "x.com"),
}

#: Rental durations offered as one-tap buttons, in hours.
RENTAL_PRESET_HOURS: tuple[int, ...] = (4, 12, 24, 72, 168, 720)

#: Items per page for every paginated list.
PAGE_SIZE = 16

#: Buttons per row in paginated grids.
GRID_COLUMNS = 2
