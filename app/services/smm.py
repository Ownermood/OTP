"""SMM panel: catalogue, ordering and status tracking.

Mirrors the SMS purchase path -- price re-quoted from the live catalogue,
wallet debited with the order in one transaction, provider called last, refund
on failure -- so the money guarantees are identical for both product lines.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.constants import OrderKind, OrderStatus, SmmCategory, TransactionType
from app.core.exceptions import (
    InsufficientBalanceError,
    OrderNotFoundError,
    ProviderError,
    ValidationError,
)
from app.core.logging import get_logger
from app.database.models import Order
from app.database.repositories import OrderRepository, UserRepository
from app.providers.base import BaseSMMProvider
from app.providers.base import SmmService as ProviderSmmService
from app.services.pricing import PriceBreakdown, PricingService
from app.services.wallet import WalletService
from app.utils.cache import TTLCache

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SmmPurchase:
    order: Order
    balance_after: int


class SmmService:
    """The SMM half of the marketplace. Disabled entirely when ``SMM_ENABLED=false``."""

    def __init__(
        self,
        session: AsyncSession,
        provider: BaseSMMProvider | None,
        pricing: PricingService,
        wallet: WalletService,
        settings: Settings,
        catalog_cache: TTLCache[list[ProviderSmmService]] | None = None,
    ) -> None:
        self._session = session
        self._provider = provider
        self._pricing = pricing
        self._wallet = wallet
        self._settings = settings
        self._orders = OrderRepository(session)
        self._users = UserRepository(session)
        self._cache = catalog_cache

    @property
    def enabled(self) -> bool:
        return self._provider is not None

    # -- catalogue ------------------------------------------------------

    async def services(self) -> list[ProviderSmmService]:
        if self._provider is None:
            return []
        if self._cache is not None:
            return await self._cache.get()
        return await self._provider.get_services()

    async def categories(self) -> list[tuple[SmmCategory, int]]:
        """Platforms that actually have services, with their counts."""
        counts: dict[str, int] = {}
        for service in await self.services():
            counts[service.category] = counts.get(service.category, 0) + 1
        ordered = [
            (category, counts.get(category.value, 0))
            for category in SmmCategory
            if counts.get(category.value)
        ]
        return ordered

    async def services_in(self, category: str) -> list[ProviderSmmService]:
        return [s for s in await self.services() if s.category == category]

    async def find_service(self, service_id: str) -> ProviderSmmService | None:
        return next((s for s in await self.services() if s.service_id == service_id), None)

    async def search(self, query: str) -> list[ProviderSmmService]:
        needle = query.lower()
        return [s for s in await self.services() if needle in s.name.lower()]

    def quote(self, service: ProviderSmmService, quantity: int) -> PriceBreakdown:
        """Price ``quantity`` units of ``service``, validating the bounds first."""
        if not service.min_quantity <= quantity <= service.max_quantity:
            raise ValidationError(
                "quantity out of range", minimum=service.min_quantity, maximum=service.max_quantity
            )
        return self._pricing.quote_smm(service.rate_per_1000, quantity)

    # -- ordering -------------------------------------------------------

    async def create_order(
        self, user_id: int, service_id: str, link: str, quantity: int, quoted_price: int
    ) -> SmmPurchase:
        """Place an SMM order, charging the user only for an accepted order."""
        if self._provider is None:
            raise ValidationError("SMM module is disabled")

        service = await self.find_service(service_id)
        if service is None:
            raise ValidationError("service is no longer offered")

        # Re-quote live: the panel's rates change without warning.
        breakdown = self.quote(service, quantity)
        if breakdown.total > quoted_price:
            quoted_price = breakdown.total

        user = await self._users.get(user_id)
        if user is None or user.balance < quoted_price:
            raise InsufficientBalanceError(
                "balance too low", required=quoted_price, available=user.balance if user else 0
            )

        order = await self._orders.create(
            user_id=user_id,
            kind=OrderKind.SMM,
            status=OrderStatus.PENDING,
            provider=self._provider.name,
            service_code=service.service_id,
            service_name=service.name,
            price=quoted_price,
            provider_cost=breakdown.provider_cost,
            link=link,
            quantity=quantity,
        )
        change = await self._wallet.debit(
            user_id,
            quoted_price,
            TransactionType.PURCHASE,
            idempotency_key=f"purchase:order:{order.id}",
            reference=f"order #{order.id}",
            description=f"SMM: {service.name} ×{quantity}",
        )
        await self._session.commit()

        try:
            provider_order_id = await self._provider.create_order(service_id, link, quantity)
        except ProviderError:
            await self._refund_and_fail(order, "SMM panel rejected the order")
            raise

        order.provider_order_id = provider_order_id
        order.status = OrderStatus.PROCESSING
        await self._session.commit()

        logger.info(
            "smm.order_created",
            order_id=order.id,
            user_id=user_id,
            service=service_id,
            quantity=quantity,
            provider_order_id=provider_order_id,
        )
        return SmmPurchase(order, change.balance_after)

    async def refresh_status(self, order: Order) -> Order:
        """Poll one SMM order and persist whatever changed."""
        if self._provider is None or not order.provider_order_id:
            return order
        if OrderStatus(order.status).is_final:
            return order

        status = await self._provider.get_order_status(order.provider_order_id)
        order.start_count = status.start_count
        order.remains = status.remains

        if status.state == "success":
            order.status = OrderStatus.SUCCESS
        elif status.state in ("cancelled", "failed"):
            # The panel will not deliver, so the user gets their money back.
            await self._refund_once(order, OrderStatus.CANCELLED, "cancelled by SMM panel")
        elif status.state == "partial":
            order.status = OrderStatus.SUCCESS
        else:
            order.status = OrderStatus.PROCESSING

        await self._session.commit()
        return order

    async def get_owned(self, order_id: int, user_id: int) -> Order:
        order = await self._orders.get_owned(order_id, user_id)
        if order is None or order.kind != OrderKind.SMM:
            raise OrderNotFoundError(f"order {order_id}")
        return order

    async def open_orders(self):
        return await self._orders.list_open(OrderKind.SMM)

    async def _refund_once(self, order: Order, status: OrderStatus, reason: str) -> None:
        if order.refunded_at is None:
            change = await self._wallet.refund(order.user_id, order.price, order.id, reason)
            if change.applied:
                from datetime import datetime

                order.refunded_at = datetime.utcnow()
        order.status = status

    async def _refund_and_fail(self, order: Order, reason: str) -> None:
        await self._refund_once(order, OrderStatus.FAILED, reason)
        await self._session.commit()
        logger.warning("smm.order_failed", order_id=order.id, reason=reason)
