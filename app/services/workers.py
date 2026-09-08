"""Background workers.

Three loops run alongside the dispatcher:

* :class:`SmsWorker` polls open activations and rentals for their SMS.
* :class:`PaymentWorker` polls pending invoices and expires stale ones.
* :class:`HealthWorker` watches provider reachability and our provider balance.

They all follow the same discipline: one database session per tick, every
iteration wrapped so a single bad order cannot kill the loop, and a sleep that
backs off when there is nothing to do -- controlled polling, not hammering.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.core.constants import OrderKind, OrderStatus
from app.core.logging import get_logger
from app.core.money import format_money, to_minor
from app.providers.base import BasePaymentProvider, BaseSMMProvider, BaseSMSProvider
from app.services.notifications import NotificationService

logger = get_logger(__name__)

#: When nothing is in flight, sleep this long instead of the tight interval.
IDLE_INTERVAL = 30

#: How long an order may sit without a provider id before it is treated as
#: orphaned. Comfortably longer than a provider call, so a purchase in flight
#: is never swept out from under itself.
ORPHAN_GRACE_SECONDS = 180


class BaseWorker:
    """A cancellable loop with crash isolation per tick."""

    name = "worker"

    def __init__(self, interval: int) -> None:
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop(), name=self.name)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            delay = self._interval
            try:
                delay = await self.tick() or self._interval
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # One bad tick must never end the loop.
                logger.error("worker.tick_failed", worker=self.name, error=str(exc), exc_info=True)
            await asyncio.sleep(delay)

    async def tick(self) -> int | None:
        """Run one iteration. Return a sleep override, or ``None`` for the default."""
        raise NotImplementedError


class SmsWorker(BaseWorker):
    """Polls activations for their SMS, and rentals for new messages."""

    name = "sms_worker"

    def __init__(
        self,
        session_factory: async_sessionmaker,
        provider: BaseSMSProvider,
        notifications: NotificationService,
        settings: Settings,
        renderer,
    ) -> None:
        super().__init__(settings.sms_poll_interval)
        self._session_factory = session_factory
        self._provider = provider
        self._notifications = notifications
        self._settings = settings
        self._render = renderer

    async def tick(self) -> int | None:
        # Imported here to keep the service layer free of circular imports.
        from app.database.repositories import OrderRepository
        from app.services.orders import OrderService
        from app.services.pricing import PricingService
        from app.services.wallet import WalletService

        async with self._session_factory() as session:
            orders = list(await OrderRepository(session).list_open(OrderKind.ACTIVATION))
            rentals = list(await OrderRepository(session).list_open(OrderKind.RENTAL))
            if not orders and not rentals:
                return IDLE_INTERVAL

            wallet = WalletService(session)
            service = OrderService(
                session, self._provider, PricingService(self._settings), wallet, self._settings
            )

            for order in orders:
                if await self._sweep_orphan(service, order):
                    continue
                await self._poll_activation(service, order)
            for rental in rentals:
                if await self._sweep_orphan(service, rental):
                    continue
                await self._poll_rental(session, rental)
        return None

    async def _sweep_orphan(self, service, order) -> bool:
        """Refund an order that was charged for but never reached the provider.

        A crash between the wallet debit and the provider call leaves the order
        with no provider id and no expiry, so no other path would ever resolve
        it and the user stays charged for nothing. True when handled here.
        """
        if order.provider_order_id:
            return False
        if order.created_at > datetime.utcnow() - timedelta(seconds=ORPHAN_GRACE_SECONDS):
            # Still young enough that a purchase may be mid-flight right now.
            return False

        await service.fail_orphan(order)
        await self._notifications.notify_user(
            order.user_id, self._render("sms.failed", order=order), essential=True
        )
        return True

    async def _poll_activation(self, service, order) -> None:
        if order.expires_at and order.expires_at < datetime.utcnow():
            await service.expire(order)
            await self._notifications.notify_user(
                order.user_id, self._render("sms.expired", order=order), essential=True
            )
            return
        if not order.provider_order_id:
            return

        try:
            status = await self._provider.get_activation_status(order.provider_order_id)
        except Exception as exc:
            logger.warning("sms.poll_failed", order_id=order.id, error=str(exc))
            return

        if status.state == "received":
            await service.mark_sms_received(order, status.code, status.text)
            await self._notifications.notify_user(
                order.user_id,
                self._render("sms.received", order=order, code=status.code, text=status.text),
                essential=True,
            )
        elif status.state in ("cancelled", "expired"):
            await service.refund_provider_cancelled(order)
            await self._notifications.notify_user(
                order.user_id, self._render("sms.cancelled", order=order), essential=True
            )

    async def _poll_rental(self, session, rental) -> None:
        if rental.expires_at and rental.expires_at < datetime.utcnow():
            rental.status = OrderStatus.EXPIRED
            rental.completed_at = datetime.utcnow()
            await session.commit()
            return
        if not rental.provider_order_id:
            return

        try:
            messages = await self._provider.get_rental_messages(rental.provider_order_id)
        except Exception as exc:
            logger.warning("rental.poll_failed", order_id=rental.id, error=str(exc))
            return

        if not messages:
            return

        # Only forward what we have not forwarded before: the stored text is
        # the running log, so comparing against it dedupes re-delivered SMS.
        seen = rental.sms_text or ""
        fresh = [m for m in messages if m.text not in seen]
        if not fresh:
            return

        rental.sms_text = "\n".join([seen, *[m.text for m in fresh]]).strip()
        await session.commit()
        for message in fresh:
            await self._notifications.notify_user(
                rental.user_id,
                self._render("rental.message", order=rental, message=message),
                essential=True,
            )


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


class SmmWorker(BaseWorker):
    """Polls open SMM orders for delivery progress."""

    name = "smm_worker"

    def __init__(
        self,
        session_factory: async_sessionmaker,
        provider: BaseSMMProvider,
        notifications: NotificationService,
        settings: Settings,
        renderer,
    ) -> None:
        super().__init__(settings.smm_poll_interval)
        self._session_factory = session_factory
        self._provider = provider
        self._notifications = notifications
        self._settings = settings
        self._render = renderer

    async def tick(self) -> int | None:
        from app.services.pricing import PricingService
        from app.services.smm import SmmService
        from app.services.wallet import WalletService

        async with self._session_factory() as session:
            service = SmmService(
                session,
                self._provider,
                PricingService(self._settings),
                WalletService(session),
                self._settings,
            )
            orders = list(await service.open_orders())
            if not orders:
                return IDLE_INTERVAL

            for order in orders:
                previous = OrderStatus(order.status)
                try:
                    await service.refresh_status(order)
                except Exception as exc:
                    logger.warning("smm.poll_failed", order_id=order.id, error=str(exc))
                    continue
                if OrderStatus(order.status) != previous and OrderStatus(order.status).is_final:
                    await self._notifications.notify_user(
                        order.user_id, self._render("smm.finished", order=order), essential=True
                    )
        return None


class HealthWorker(BaseWorker):
    """Watches provider health and our upstream balance, alerting admins."""

    name = "health_worker"

    def __init__(
        self,
        sms_provider: BaseSMSProvider,
        notifications: NotificationService,
        settings: Settings,
        bot: Bot,
        interval: int = 600,
    ) -> None:
        super().__init__(interval)
        self._provider = sms_provider
        self._notifications = notifications
        self._settings = settings
        self._bot = bot
        self._alerted_down = False
        self._alerted_low_balance = False

    async def tick(self) -> int | None:
        try:
            balance = await self._provider.get_balance()
        except Exception as exc:
            if not self._alerted_down:
                self._alerted_down = True
                await self._notifications.notify_admins(
                    f"🚨 <b>Provider unavailable</b>\n\n{self._provider.name}: {exc}"
                )
            logger.error("health.provider_down", provider=self._provider.name, error=str(exc))
            return None

        if self._alerted_down:
            self._alerted_down = False
            await self._notifications.notify_admins(
                f"✅ <b>Provider recovered</b>\n\n{self._provider.name} is answering again."
            )

        threshold = to_minor(self._settings.sms_provider_low_balance_threshold)
        if threshold and balance < threshold:
            if not self._alerted_low_balance:
                self._alerted_low_balance = True
                await self._notifications.notify_admins(
                    "⚠️ <b>Low provider balance</b>\n\n"
                    f"Current: {format_money(balance, self._settings.currency_symbol)}\n"
                    f"Threshold: {format_money(threshold, self._settings.currency_symbol)}"
                )
        else:
            self._alerted_low_balance = False
        return None
