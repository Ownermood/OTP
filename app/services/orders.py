"""Order lifecycle for SMS activations and rentals.

The purchase path is where most of the bug-prevention requirements land, so the
ordering of steps in :meth:`OrderService.purchase_activation` is deliberate:

1. Re-read the live price from the provider -- the quote the user saw may be
   stale, and the quoted price is *never* trusted for charging.
2. Reject a second identical in-flight order, which is what a double tap
   produces.
3. Debit the wallet and create the order inside one transaction.
4. Only then call the provider. If that call fails, refund and mark the order
   failed -- the user is never charged for a number they did not get.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.constants import OrderKind, OrderStatus, TransactionType
from app.core.exceptions import (
    DuplicateOperationError,
    InsufficientBalanceError,
    OrderNotFoundError,
    ProviderError,
    StalePriceError,
    ValidationError,
)
from app.core.logging import get_logger
from app.database.models import Order
from app.database.repositories import OrderRepository, UserRepository
from app.providers.base import BaseSMSProvider
from app.services.pricing import PricingService
from app.services.wallet import WalletService

logger = get_logger(__name__)

#: How far the live price may drift from the quote before we re-confirm, in
#: minor units. Small upward drift is absorbed rather than nagging the user.
PRICE_TOLERANCE = 100


@dataclass(frozen=True, slots=True)
class PurchaseResult:
    order: Order
    balance_after: int


class OrderService:
    def __init__(
        self,
        session: AsyncSession,
        provider: BaseSMSProvider,
        pricing: PricingService,
        wallet: WalletService,
        settings: Settings,
    ) -> None:
        self._session = session
        self._provider = provider
        self._pricing = pricing
        self._wallet = wallet
        self._settings = settings
        self._orders = OrderRepository(session)
        self._users = UserRepository(session)

    # -- purchase -------------------------------------------------------

    async def purchase_activation(
        self,
        user_id: int,
        service_code: str,
        service_name: str,
        country_id: int,
        country_name: str,
        quoted_price: int,
    ) -> PurchaseResult:
        """Buy one activation. See the module docstring for why the order matters."""
        # 1. Authoritative price, straight from the provider.
        live_cost = await self._provider.get_price(service_code, country_id)
        price = self._pricing.quote(live_cost).total
        if price > quoted_price + PRICE_TOLERANCE:
            raise StalePriceError("price moved", quoted=quoted_price, actual=price)

        # 2. Double-click / duplicate protection.
        if await self._orders.has_open_order(user_id, service_code, country_id):
            raise DuplicateOperationError("identical activation already in flight")

        user = await self._users.get(user_id)
        if user is None or user.balance < price:
            raise InsufficientBalanceError(
                "balance too low", required=price, available=user.balance if user else 0
            )

        # 3. Charge and record the order atomically.
        order = await self._orders.create(
            user_id=user_id,
            kind=OrderKind.ACTIVATION,
            status=OrderStatus.PENDING,
            provider=self._provider.name,
            service_code=service_code,
            service_name=service_name,
            country_id=country_id,
            country_name=country_name,
            price=price,
            provider_cost=live_cost,
        )
        change = await self._wallet.debit(
            user_id,
            price,
            TransactionType.PURCHASE,
            idempotency_key=f"purchase:order:{order.id}",
            reference=f"order #{order.id}",
            description=f"{service_name} — {country_name}",
        )
        await self._session.commit()

        # 4. Buy from the provider, refunding if it refuses.
        try:
            activation = await self._provider.create_activation(service_code, country_id)
        except ProviderError:
            await self._fail_and_refund(order, reason="provider rejected the purchase")
            raise

        order.provider_order_id = activation.provider_order_id
        order.phone = activation.phone
        order.status = OrderStatus.PROCESSING
        order.expires_at = activation.expires_at or (
            datetime.utcnow() + timedelta(seconds=self._settings.sms_timeout)
        )
        if activation.cost:
            order.provider_cost = activation.cost
        await self._session.commit()

        logger.info(
            "order.created",
            order_id=order.id,
            user_id=user_id,
            service=service_code,
            country=country_id,
            price=price,
            provider_order_id=activation.provider_order_id,
        )
        return PurchaseResult(order, change.balance_after)

    async def purchase_rental(
        self,
        user_id: int,
        service_code: str,
        service_name: str,
        country_id: int,
        country_name: str,
        hours: int,
        quoted_price: int,
    ) -> PurchaseResult:
        """Rent a number for ``hours``. Same safety ordering as an activation."""
        if not self._settings.rental_enabled:
            raise ValidationError("rentals are disabled")
        if not self._settings.min_rental_hours <= hours <= self._settings.max_rental_hours:
            raise ValidationError("rental duration out of range")

        user = await self._users.get(user_id)
        if user is None or user.balance < quoted_price:
            raise InsufficientBalanceError(
                "balance too low", required=quoted_price, available=user.balance if user else 0
            )

        order = await self._orders.create(
            user_id=user_id,
            kind=OrderKind.RENTAL,
            status=OrderStatus.PENDING,
            provider=self._provider.name,
            service_code=service_code,
            service_name=service_name,
            country_id=country_id,
            country_name=country_name,
            price=quoted_price,
            rental_hours=hours,
        )
        change = await self._wallet.debit(
            user_id,
            quoted_price,
            TransactionType.PURCHASE,
            idempotency_key=f"purchase:order:{order.id}",
            reference=f"order #{order.id}",
            description=f"Rental {service_name} — {country_name} ({hours}h)",
        )
        await self._session.commit()

        try:
            rental = await self._provider.create_rental(service_code, country_id, hours)
        except ProviderError:
            await self._fail_and_refund(order, reason="provider rejected the rental")
            raise

        order.provider_order_id = rental.provider_order_id
        order.phone = rental.phone
        order.status = OrderStatus.PROCESSING
        order.expires_at = rental.expires_at
        if rental.cost:
            order.provider_cost = rental.cost
        await self._session.commit()

        logger.info("rental.created", order_id=order.id, user_id=user_id, hours=hours)
        return PurchaseResult(order, change.balance_after)

    # -- lifecycle ------------------------------------------------------

    async def cancel(self, order_id: int, user_id: int) -> Order:
        """Cancel an SMS order the user owns and refund it, exactly once.

        The release call is chosen by order kind. Sending a rental id or an SMM
        panel id to ``cancel_activation`` would release the wrong thing
        upstream while still refunding the user, so the kind is checked here
        rather than trusted from whichever keyboard produced the callback.
        """
        order = await self._orders.get_owned(order_id, user_id)
        if order is None:
            raise OrderNotFoundError(f"order {order_id}")
        if OrderKind(order.kind) is OrderKind.SMM:
            # SMM delivery has already started at the panel; there is nothing
            # to release, and refunding a delivered order is a straight loss.
            raise ValidationError("SMM orders cannot be cancelled")
        if OrderStatus(order.status).is_final:
            raise DuplicateOperationError("order already closed")

        if order.provider_order_id:
            try:
                if OrderKind(order.kind) is OrderKind.RENTAL:
                    await self._provider.cancel_rental(order.provider_order_id)
                else:
                    await self._provider.cancel_activation(order.provider_order_id)
            except (ProviderError, NotImplementedError) as exc:
                # The refund still happens: we charged the user, so we own the risk.
                logger.warning("order.cancel_upstream_failed", order_id=order.id, error=str(exc))

        await self._refund_once(order, OrderStatus.CANCELLED, "cancelled by user")
        await self._session.commit()
        return order

    async def fail_orphan(self, order: Order) -> None:
        """Close out an order that was charged for but never reached the provider.

        A crash between the wallet debit and the provider call leaves an order
        PENDING with no provider id and no expiry, so nothing else would ever
        resolve it and the user stays charged. The sweep in the SMS worker
        hands those here.
        """
        if OrderStatus(order.status).is_final or order.provider_order_id:
            return
        await self._refund_once(order, OrderStatus.FAILED, "never reached the provider")
        await self._session.commit()
        logger.warning("order.orphan_refunded", order_id=order.id, user_id=order.user_id)

    async def mark_sms_received(self, order: Order, code: str | None, text: str | None) -> None:
        """Record the SMS and close the order out successfully."""
        if OrderStatus(order.status).is_final:
            return
        order.sms_code = code
        order.sms_text = text
        order.status = OrderStatus.SUCCESS
        order.completed_at = datetime.utcnow()
        if order.provider_order_id:
            try:
                await self._provider.finish_activation(order.provider_order_id)
            except ProviderError as exc:
                logger.warning("order.finish_failed", order_id=order.id, error=str(exc))
        await self._session.commit()
        logger.info("order.completed", order_id=order.id)

    async def expire(self, order: Order) -> None:
        """Close an order that timed out without an SMS, refunding the user."""
        if OrderStatus(order.status).is_final:
            return
        if order.provider_order_id:
            try:
                await self._provider.cancel_activation(order.provider_order_id)
            except ProviderError:
                pass
        await self._refund_once(order, OrderStatus.EXPIRED, "no SMS received in time")
        await self._session.commit()
        logger.info("order.expired", order_id=order.id)

    async def refund_provider_cancelled(self, order: Order) -> None:
        """The provider dropped the activation; refund and close."""
        if OrderStatus(order.status).is_final:
            return
        await self._refund_once(order, OrderStatus.REFUNDED, "cancelled by provider")
        await self._session.commit()

    # -- reads ----------------------------------------------------------

    async def get_owned(self, order_id: int, user_id: int) -> Order:
        order = await self._orders.get_owned(order_id, user_id)
        if order is None:
            raise OrderNotFoundError(f"order {order_id}")
        return order

    async def list_for_user(self, user_id: int, kind: OrderKind | None = None):
        return await self._orders.list_for_user(user_id, kind)

    async def recently_used(self, user_id: int):
        return await self._orders.recently_used(user_id)

    # -- internals ------------------------------------------------------

    async def _refund_once(self, order: Order, status: OrderStatus, reason: str) -> None:
        """Refund an order's price and set its final status.

        ``refunded_at`` plus the wallet's idempotency key mean a refund cannot
        run twice even if the poller and the user race each other.
        """
        if order.refunded_at is None:
            change = await self._wallet.refund(order.user_id, order.price, order.id, reason)
            if change.applied:
                order.refunded_at = datetime.utcnow()
        order.status = status
        order.completed_at = datetime.utcnow()

    async def _fail_and_refund(self, order: Order, reason: str) -> None:
        await self._refund_once(order, OrderStatus.FAILED, reason)
        await self._session.commit()
        logger.warning("order.failed", order_id=order.id, reason=reason)
