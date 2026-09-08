"""ORM models.

Money columns are ``Integer`` **minor units** throughout -- never Float. Two
constraints do real safety work rather than documentation work:

* ``uq_payments_provider_invoice`` makes a replayed payment webhook impossible
  to credit twice.
* ``uq_transactions_idempotency_key`` makes every balance movement -- purchase,
  refund, referral payout -- exactly-once, keyed by the operation that caused it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    AdminRole,
    OrderKind,
    OrderStatus,
    PaymentStatus,
    TransactionType,
)
from app.database.base import Base, IntPK, TelegramId, TimestampMixin


class User(Base, TimestampMixin):
    """A Telegram user and their wallet."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(TelegramId, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), index=True)
    full_name: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)

    #: Spendable balance in minor units. Only ever changed by WalletService.
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Lifetime referral earnings, for display. Already included in `balance`.
    referral_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ban_reason: Mapped[str | None] = mapped_column(String(256))
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: A redeemed percent promo waiting for the user's next qualifying deposit.
    pending_promo_id: Mapped[int | None] = mapped_column(Integer)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    orders: Mapped[list[Order]] = relationship(back_populates="user", lazy="raise")


class Order(Base, IntPK, TimestampMixin):
    """An activation, rental or SMM order.

    One table for all three kinds keeps "My Orders" and the admin search simple;
    the kind-specific columns are nullable and documented below.
    """

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_user_status", "user_id", "status"),
        UniqueConstraint("kind", "provider", "provider_order_id", name="uq_orders_provider_order"),
    )

    user_id: Mapped[int] = mapped_column(
        TelegramId, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[OrderKind] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[OrderStatus] = mapped_column(
        String(16), default=OrderStatus.PENDING, nullable=False, index=True
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Upstream id -- kept so support can trace an order in the provider's panel.
    provider_order_id: Mapped[str | None] = mapped_column(String(64), index=True)

    #: What was bought. For SMS: service code + country; for SMM: service id + link.
    service_code: Mapped[str] = mapped_column(String(64), nullable=False)
    service_name: Mapped[str] = mapped_column(String(128), nullable=False)
    country_id: Mapped[int | None] = mapped_column(Integer, index=True)
    country_name: Mapped[str | None] = mapped_column(String(64))

    #: What the user paid, and what we paid the provider (both minor units).
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- activation / rental ---
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    sms_code: Mapped[str | None] = mapped_column(String(32))
    sms_text: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    rental_hours: Mapped[int | None] = mapped_column(Integer)

    # --- SMM ---
    link: Mapped[str | None] = mapped_column(String(512))
    quantity: Mapped[int | None] = mapped_column(Integer)
    start_count: Mapped[int | None] = mapped_column(Integer)
    remains: Mapped[int | None] = mapped_column(Integer)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    #: Set once a refund has been issued, so a refund can never run twice.
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped[User] = relationship(back_populates="orders", lazy="raise")


class Transaction(Base, IntPK, TimestampMixin):
    """An immutable audit record of a single balance movement.

    ``idempotency_key`` is what prevents double-charging and double-refunding:
    the caller derives it from the operation (``purchase:41``, ``refund:41``,
    ``referral:payment:9``) and the unique index rejects the second attempt.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_transactions_idempotency_key"),
        Index("ix_transactions_user_type", "user_id", "type"),
    )

    user_id: Mapped[int] = mapped_column(
        TelegramId, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[TransactionType] = mapped_column(String(24), nullable=False)
    #: Signed: positive credits the user, negative debits them.
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_before: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    #: Human-readable pointer to the cause, e.g. ``order #41`` or ``@someone``.
    reference: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(String(256))


class Payment(Base, IntPK, TimestampMixin):
    """A deposit invoice.

    ``(provider, invoice_id)`` is unique, so a webhook or poll that reports the
    same invoice twice resolves to the same row and credits the wallet once.
    """

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "invoice_id", name="uq_payments_provider_invoice"),
    )

    user_id: Mapped[int] = mapped_column(
        TelegramId, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    invoice_id: Mapped[str] = mapped_column(String(128), nullable=False)

    #: Credited amount in our currency's minor units.
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    #: What the user actually pays upstream, in the provider's own unit.
    provider_amount: Mapped[str] = mapped_column(String(32), default="0", nullable=False)
    currency: Mapped[str] = mapped_column(String(16), default="INR", nullable=False)

    status: Mapped[PaymentStatus] = mapped_column(
        String(16), default=PaymentStatus.PENDING, nullable=False, index=True
    )
    pay_url: Mapped[str | None] = mapped_column(String(512))
    #: Invoice message, so it can be edited/removed once payment lands.
    message_id: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)

    # --- manual (UPI / bank) deposits ---
    #: Telegram file id of the payment screenshot the user submitted.
    proof_file_id: Mapped[str | None] = mapped_column(String(256))
    #: Message id of the review post, so the decision can be written back to it.
    review_message_id: Mapped[int | None] = mapped_column(Integer)
    reviewed_by: Mapped[int | None] = mapped_column(TelegramId)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_note: Mapped[str | None] = mapped_column(String(256))


class Favorite(Base, IntPK, TimestampMixin):
    """A saved service+country combination."""

    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "service_code", "country_id", name="uq_favorites_combo"),
    )

    user_id: Mapped[int] = mapped_column(
        TelegramId, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_code: Mapped[str] = mapped_column(String(64), nullable=False)
    service_name: Mapped[str] = mapped_column(String(128), nullable=False)
    country_id: Mapped[int] = mapped_column(Integer, nullable=False)
    country_name: Mapped[str] = mapped_column(String(64), nullable=False)


class Referral(Base, IntPK, TimestampMixin):
    """Links an invited user to their inviter. One row per invited user."""

    __tablename__ = "referrals"
    __table_args__ = (UniqueConstraint("invited_id", name="uq_referrals_invited"),)

    inviter_id: Mapped[int] = mapped_column(
        TelegramId, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invited_id: Mapped[int] = mapped_column(
        TelegramId, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PromoCode(Base, IntPK, TimestampMixin):
    """A redeemable bonus code."""

    __tablename__ = "promo_codes"
    __table_args__ = (UniqueConstraint("code", name="uq_promo_codes_code"),)

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Flat bonus in minor units. Ignored when ``percent`` is set.
    amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Percentage bonus applied to the user's next deposit, when set.
    percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_activations: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_deposit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(TelegramId)


class PromoUsage(Base, IntPK, TimestampMixin):
    """One redemption of a promo code. Unique per (code, user)."""

    __tablename__ = "promo_usages"
    __table_args__ = (UniqueConstraint("promo_id", "user_id", name="uq_promo_usages_once"),)

    promo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("promo_codes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        TelegramId, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AdminAction(Base, IntPK, TimestampMixin):
    """Audit log of privileged actions. Written for every manual change."""

    __tablename__ = "admin_actions"

    admin_id: Mapped[int] = mapped_column(TelegramId, nullable=False, index=True)
    role: Mapped[AdminRole] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[str | None] = mapped_column(Text)


class Setting(Base):
    """Runtime settings an admin can flip without a redeploy (maintenance mode…)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
