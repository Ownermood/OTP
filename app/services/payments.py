"""Deposits.

The one rule this module exists to enforce: **a payment credits a wallet
exactly once**, no matter how many times the provider tells us about it. Three
layers make that true:

* ``(provider, invoice_id)`` is unique, so the invoice resolves to one row.
* Settlement refuses to run on a row that is not ``PENDING``.
* The wallet credit is keyed ``deposit:<provider>:<invoice_id>``, so even a
  concurrent double-settle moves the balance once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.constants import PaymentStatus, TransactionType
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.core.money import to_minor
from app.database.models import Payment
from app.database.repositories import PaymentRepository
from app.providers.base import BasePaymentProvider
from app.services.promo import PromoService
from app.services.referrals import ReferralService
from app.services.wallet import WalletService

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Settlement:
    """Outcome of settling an invoice."""

    payment: Payment
    #: False when this was a replay and the balance did not move.
    credited: bool
    balance_after: int


class PaymentService:
    def __init__(
        self,
        session: AsyncSession,
        providers: dict[str, BasePaymentProvider],
        wallet: WalletService,
        referrals: ReferralService,
        settings: Settings,
        promo: PromoService | None = None,
    ) -> None:
        self._session = session
        self._providers = providers
        self._wallet = wallet
        self._referrals = referrals
        self._promo = promo or PromoService(session, wallet)
        self._settings = settings
        self._payments = PaymentRepository(session)

    def provider(self, name: str) -> BasePaymentProvider:
        provider = self._providers.get(name)
        if provider is None:
            raise ValidationError(f"payment provider {name} is not enabled")
        return provider

    @property
    def available(self) -> dict[str, BasePaymentProvider]:
        return self._providers

    def validate_amount(self, amount: int) -> None:
        """Enforce the configured deposit bounds."""
        if amount < to_minor(self._settings.min_deposit):
            raise ValidationError("below minimum deposit")
        if amount > to_minor(self._settings.max_deposit):
            raise ValidationError("above maximum deposit")

    async def create_invoice(self, user_id: int, provider_name: str, amount: int) -> Payment:
        """Create an invoice upstream and record it locally."""
        self.validate_amount(amount)
        provider = self.provider(provider_name)
        invoice = await provider.create_invoice(
            user_id, amount, f"{self._settings.service_name} balance top-up"
        )
        payment = await self._payments.create(
            user_id=user_id,
            provider=provider.name,
            invoice_id=invoice.invoice_id,
            amount=amount,
            provider_amount=invoice.provider_amount,
            currency=self._settings.currency_code,
            status=PaymentStatus.PENDING,
            pay_url=invoice.pay_url,
            expires_at=invoice.expires_at,
        )
        await self._session.commit()
        logger.info(
            "payment.invoice_created",
            payment_id=payment.id,
            user_id=user_id,
            provider=provider.name,
            amount=amount,
        )
        return payment

    async def settle(self, provider_name: str, invoice_id: str) -> Settlement | None:
        """Credit a paid invoice. Idempotent; returns ``None`` if unknown."""
        payment = await self._payments.get_by_invoice(provider_name, invoice_id)
        if payment is None:
            logger.warning("payment.unknown_invoice", provider=provider_name, invoice=invoice_id)
            return None

        # EXPIRED is settleable: we may have stopped waiting, but if the gateway
        # now says the money arrived, keeping it uncredited is the worse error.
        # PAID and REFUNDED are terminal -- that is where a replay stops.
        if payment.status not in (PaymentStatus.PENDING, PaymentStatus.EXPIRED):
            logger.info("payment.replay_ignored", payment_id=payment.id, status=payment.status)
            return Settlement(payment, credited=False, balance_after=await self._balance(payment))

        if payment.status == PaymentStatus.EXPIRED:
            logger.warning(
                "payment.late_settlement",
                payment_id=payment.id,
                user_id=payment.user_id,
                amount=payment.amount,
            )

        change = await self._wallet.credit(
            payment.user_id,
            payment.amount,
            TransactionType.DEPOSIT,
            idempotency_key=f"deposit:{provider_name}:{invoice_id}",
            reference=f"payment #{payment.id}",
            description=f"Deposit via {provider_name}",
        )
        payment.status = PaymentStatus.PAID
        payment.paid_at = datetime.utcnow()
        await self._session.commit()

        if change.applied:
            # Both payouts are keyed on this payment, so a replayed settlement
            # that somehow reaches here still pays each of them once.
            await self._referrals.pay_commission(payment.user_id, payment.amount, payment.id)
            await self._promo.apply_deposit_bonus(payment.user_id, payment.amount, payment.id)
            await self._session.commit()

        logger.info(
            "payment.settled",
            payment_id=payment.id,
            user_id=payment.user_id,
            amount=payment.amount,
            credited=change.applied,
        )
        return Settlement(payment, change.applied, change.balance_after)

    async def mark_failed(self, payment: Payment, status: PaymentStatus) -> None:
        payment.status = status
        await self._session.commit()

    async def get_pending(self, provider_name: str):
        return await self._payments.list_pending(provider_name)

    async def expire_stale(self) -> int:
        closed = await self._payments.expire_stale(self._settings.payment_grace_hours)
        if closed:
            await self._session.commit()
        return closed

    async def list_for_user(self, user_id: int):
        return await self._payments.list_for_user(user_id)

    async def _balance(self, payment: Payment) -> int:
        return await self._wallet.get_balance(payment.user_id)
