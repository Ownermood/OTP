"""Manually reviewed deposits (UPI, bank transfer, anything off-platform).

The user pays outside the bot, then submits the amount, the transaction
reference (UTR) and a screenshot. The request is posted to a review channel and
**no balance moves until a reviewer approves it**.

Two properties do the real work here:

* The UTR is stored as the payment's ``invoice_id``, so the existing unique
  index on ``(provider, invoice_id)`` makes a reference physically impossible
  to submit twice -- by the same user or a different one. That is what stops a
  screenshot of one real payment being reused.
* Approval runs through the same :meth:`PaymentService.settle` as an automated
  gateway, so the credit carries an idempotency key and two reviewers tapping
  Approve at the same moment still credit once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.constants import ROLE_PERMISSIONS, AdminRole, PaymentStatus
from app.core.exceptions import (
    AccessDeniedError,
    DuplicateOperationError,
    ValidationError,
)
from app.core.logging import get_logger
from app.database.models import Payment
from app.database.repositories import AdminActionRepository, PaymentRepository
from app.services.payments import PaymentService

logger = get_logger(__name__)

PROVIDER = "manual"

#: A UTR/UPI reference: alphanumeric, long enough not to be a typo.
UTR_RE = re.compile(r"^[A-Za-z0-9]{6,32}$")

#: Manual requests wait for a human, so they are not put on a payment clock.
REVIEW_WINDOW_DAYS = 3650


@dataclass(frozen=True, slots=True)
class Decision:
    """Outcome of a review."""

    payment: Payment
    approved: bool
    #: False when the request had already been decided by someone else.
    applied: bool
    balance_after: int = 0


def normalise_utr(text: str) -> str:
    """Validate and canonicalise a transaction reference.

    Upper-cased so ``ab12cd`` and ``AB12CD`` cannot be submitted as two
    different references for the same payment.
    """
    candidate = re.sub(r"[\s-]", "", text.strip()).upper()
    if not UTR_RE.match(candidate):
        raise ValidationError("invalid transaction reference")
    return candidate


class ManualPaymentService:
    def __init__(
        self, session: AsyncSession, payments: PaymentService, settings: Settings
    ) -> None:
        self._session = session
        self._payments = payments
        self._settings = settings
        self._repo = PaymentRepository(session)
        self._actions = AdminActionRepository(session)

    @property
    def enabled(self) -> bool:
        return self._settings.manual_payment_enabled

    def can_review(self, user_id: int) -> bool:
        """Whether ``user_id`` may decide requests. Checked server-side, always.

        Gated on ``balance`` rather than ``payments``: approving a request
        creates money, so it belongs with the roles trusted to adjust a
        balance. SUPPORT can read the payment list but cannot credit from it.
        """
        role = self._settings.role_for(user_id)
        return role is not None and "balance" in ROLE_PERMISSIONS[role]

    async def submit(
        self, user_id: int, amount: int, utr: str, proof_file_id: str
    ) -> Payment:
        """Record a deposit claim awaiting review."""
        if not self.enabled:
            raise ValidationError("manual payments are disabled")
        self._payments.validate_amount(amount)

        open_requests = await self._repo.count_pending_for_user(PROVIDER, user_id)
        if open_requests >= self._settings.manual_payment_max_pending:
            raise ValidationError("too many requests awaiting review")

        try:
            # The unique (provider, invoice_id) index is the duplicate-UTR guard.
            async with self._session.begin_nested():
                payment = await self._repo.create(
                    user_id=user_id,
                    provider=PROVIDER,
                    invoice_id=utr,
                    amount=amount,
                    provider_amount=str(amount),
                    currency=self._settings.currency_code,
                    status=PaymentStatus.PENDING,
                    proof_file_id=proof_file_id,
                    expires_at=datetime.utcnow() + timedelta(days=REVIEW_WINDOW_DAYS),
                )
        except IntegrityError as exc:
            logger.warning("manual_payment.duplicate_utr", user_id=user_id, utr=utr)
            raise DuplicateOperationError("this reference was already submitted") from exc

        await self._session.commit()
        logger.info(
            "manual_payment.submitted",
            payment_id=payment.id,
            user_id=user_id,
            amount=amount,
        )
        return payment

    async def get(self, payment_id: int) -> Payment | None:
        payment = await self._repo.get(payment_id)
        return payment if payment is not None and payment.provider == PROVIDER else None

    async def set_review_message(self, payment: Payment, message_id: int) -> None:
        payment.review_message_id = message_id
        await self._session.commit()

    async def approve(self, payment_id: int, reviewer_id: int) -> Decision:
        """Credit an approved request.

        Idempotent at two levels: the status check below rejects a second
        review, and the wallet credit underneath is keyed on the payment, so a
        race between two reviewers still moves the balance once.
        """
        payment = await self._require_reviewable(payment_id, reviewer_id)
        if payment is None:
            return await self._already_decided(payment_id)

        settlement = await self._payments.settle(PROVIDER, payment.invoice_id)
        payment.reviewed_by = reviewer_id
        payment.reviewed_at = datetime.utcnow()
        await self._log(reviewer_id, "payment_approve", payment)
        await self._session.commit()

        logger.info(
            "manual_payment.approved",
            payment_id=payment.id,
            reviewer=reviewer_id,
            user_id=payment.user_id,
            amount=payment.amount,
            credited=bool(settlement and settlement.credited),
        )
        return Decision(
            payment,
            approved=True,
            applied=bool(settlement and settlement.credited),
            balance_after=settlement.balance_after if settlement else 0,
        )

    async def decline(self, payment_id: int, reviewer_id: int, reason: str = "") -> Decision:
        """Reject a request. No balance moves, and the user is told why."""
        payment = await self._require_reviewable(payment_id, reviewer_id)
        if payment is None:
            return await self._already_decided(payment_id)

        payment.status = PaymentStatus.FAILED
        payment.reviewed_by = reviewer_id
        payment.reviewed_at = datetime.utcnow()
        payment.review_note = reason[:200] or None
        await self._log(reviewer_id, "payment_decline", payment, reason)
        await self._session.commit()

        logger.info(
            "manual_payment.declined",
            payment_id=payment.id,
            reviewer=reviewer_id,
            user_id=payment.user_id,
        )
        return Decision(payment, approved=False, applied=True)

    async def pending(self, limit: int = 50):
        return await self._repo.list_pending(PROVIDER, limit)

    async def _require_reviewable(self, payment_id: int, reviewer_id: int) -> Payment | None:
        """Authorise the reviewer and return the request only if still open."""
        if not self.can_review(reviewer_id):
            raise AccessDeniedError("not a payment reviewer")

        payment = await self.get(payment_id)
        if payment is None:
            raise ValidationError("unknown request")
        if payment.status != PaymentStatus.PENDING:
            return None
        return payment

    async def _already_decided(self, payment_id: int) -> Decision:
        payment = await self.get(payment_id)
        return Decision(
            payment,  # type: ignore[arg-type]
            approved=payment.status == PaymentStatus.PAID if payment else False,
            applied=False,
        )

    async def _log(
        self, reviewer_id: int, action: str, payment: Payment, reason: str = ""
    ) -> None:
        role = self._settings.role_for(reviewer_id) or AdminRole.ADMIN
        details = f"{payment.amount} · UTR {payment.invoice_id}"
        if reason:
            details = f"{details} · {reason}"
        await self._actions.log(reviewer_id, role, action, str(payment.user_id), details)
