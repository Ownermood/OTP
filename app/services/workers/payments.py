"""Polls pending invoices and settles the ones the gateway confirms."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.core.logging import get_logger
from app.providers.base import BasePaymentProvider
from app.services.notifications import NotificationService
from app.services.workers.base import IDLE_INTERVAL, BaseWorker

logger = get_logger(__name__)

class PaymentWorker(BaseWorker):
    """Polls pending invoices and closes out expired ones."""

    name = "payment_worker"

    def __init__(
        self,
        session_factory: async_sessionmaker,
        providers: dict[str, BasePaymentProvider],
        notifications: NotificationService,
        settings: Settings,
        renderer,
    ) -> None:
        super().__init__(5)
        self._session_factory = session_factory
        self._providers = providers
        self._notifications = notifications
        self._settings = settings
        self._render = renderer

    async def tick(self) -> int | None:
        from app.services.payments import PaymentService
        from app.services.referrals import ReferralService
        from app.services.wallet import WalletService

        async with self._session_factory() as session:
            wallet = WalletService(session)
            payments = PaymentService(
                session,
                self._providers,
                wallet,
                ReferralService(session, wallet, self._settings),
                self._settings,
            )
            await payments.expire_stale()

            polled_anything = False
            for name, provider in self._providers.items():
                if not provider.supports_polling:
                    continue
                pending = list(await payments.get_pending(name))
                if not pending:
                    continue
                polled_anything = True
                await self._poll_provider(payments, provider, name, pending)

            return None if polled_anything else IDLE_INTERVAL

    async def _poll_provider(self, payments, provider, name: str, pending) -> None:
        invoice_ids = [payment.invoice_id for payment in pending]
        try:
            check_many = getattr(provider, "check_many", None)
            if check_many is not None:
                statuses = await check_many(invoice_ids)
            else:
                statuses = {
                    invoice_id: await provider.check_payment(invoice_id)
                    for invoice_id in invoice_ids
                }
        except Exception as exc:
            logger.warning("payment.poll_failed", provider=name, error=str(exc))
            return

        for payment in pending:
            if statuses.get(payment.invoice_id) != "paid":
                continue
            settlement = await payments.settle(name, payment.invoice_id)
            if settlement and settlement.credited:
                await self._announce_settlement(payments, payment, settlement)


    async def _announce_settlement(self, payments, payment, settlement) -> None:
        """Tell the depositor, and anyone who earned from the deposit."""
        await self._notifications.notify_user(
            payment.user_id,
            self._render(
                "wallet.success", amount=payment.amount, balance=settlement.balance_after
            ),
            essential=True,
        )
        if settlement.promo_bonus:
            await self._notifications.notify_user(
                payment.user_id,
                self._render(
                    "promo.deposit_bonus",
                    amount=settlement.promo_bonus,
                    balance=settlement.balance_after,
                ),
                essential=True,
            )
        if settlement.referral_commission:
            # The inviter earned money and would otherwise never be told.
            inviter_id = await payments.inviter_of(payment.user_id)
            if inviter_id is not None:
                await self._notifications.notify_user(
                    inviter_id,
                    self._render(
                        "referral.earned", amount=settlement.referral_commission
                    ),
                )
