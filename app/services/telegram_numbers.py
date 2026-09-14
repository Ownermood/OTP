"""TG-Lion Telegram numbers: its own product, its own order kind.

Mirrors the SMS/SMM purchase pattern -- price re-quoted from the live
catalogue, wallet debited with the order in one transaction, provider called
last, refund on failure -- so the money guarantees are identical to every
other product line. See :mod:`app.providers.tg_lion` for why this is not
just another :class:`~app.providers.base.BaseSMSProvider`.

TG-Lion has no provider-side cancel/finish call (see the provider module's
docstring), so :meth:`cancel` and :meth:`expire` here are entirely local
bookkeeping -- there is nothing upstream to release, only our own refund
obligation to honour. That is deliberate, not a gap: Villan owns that
guarantee itself rather than depending on a provider capability that does
not exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.constants import OrderKind, OrderStatus, TransactionType
from app.core.countries import matches_search
from app.core.exceptions import (
    DuplicateOperationError,
    InsufficientBalanceError,
    OrderNotFoundError,
    ProviderError,
)
from app.core.logging import get_logger
from app.database.models import Order
from app.database.repositories import OrderRepository, UserRepository
from app.providers.tg_lion import TgLionCountry, TgLionProvider
from app.services.pricing import PricingService
from app.services.wallet import WalletService
from app.utils.cache import TTLCache

logger = get_logger(__name__)

#: TG-Lion sells raw numbers with no service dimension, so every order shares
#: one synthetic service code/name -- purely for display, never sent upstream.
PRODUCT_CODE = "telegram_number"
PRODUCT_NAME = "Telegram Number"


@dataclass(frozen=True, slots=True)
class TelegramPurchase:
    order: Order
    balance_after: int


class TelegramNumberService:
    """The Telegram-number half of the marketplace. Disabled unless TG_LION_ENABLED=true."""

    def __init__(
        self,
        session: AsyncSession,
        provider: TgLionProvider | None,
        pricing: PricingService,
        wallet: WalletService,
        settings: Settings,
        catalog_cache: TTLCache[list[TgLionCountry]] | None = None,
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

    # -- catalogue --------------------------------------------------------

    async def countries(self) -> list[TgLionCountry]:
        if self._provider is None:
            return []
        if self._cache is not None:
            return await self._cache.get()
        return await self._provider.get_countries()

    async def find_country(self, country_code: str) -> TgLionCountry | None:
        code = country_code.strip().lower()
        return next((c for c in await self.countries() if c.code == code), None)

    async def search_countries(self, query: str) -> list[TgLionCountry]:
        """Find countries by name, ISO alpha-2/alpha-3, dial code, or TG-Lion's
        own short code -- same matching rule as the SMS-activation catalogue,
        see :func:`app.core.countries.matches_search`."""
        needle = query.strip().lower().lstrip("+")
        if not needle:
            return []
        return [c for c in await self.countries() if matches_search(c.name, needle, c.code)]

    # -- purchase -----------------------------------------------------------

    async def purchase(
        self, user_id: int, country_code: str, quoted_price: int
    ) -> TelegramPurchase:
        """Buy one Telegram number, charging the user only for a real number."""
        if self._provider is None:
            raise ProviderError("TG-Lion is not enabled")

        country = await self.find_country(country_code)
        if country is None:
            raise ProviderError(f"country {country_code!r} is no longer offered")

        # Authoritative price straight from the provider, not the TTL-cached
        # catalogue (which exists only to render the list quickly) -- the
        # same "never trust a stale price at charge time" rule OrderService
        # applies to SMS activations via a live get_price call.
        live_cost = await self._provider.get_price(country_code)
        price = self._pricing.quote(live_cost).total
        if price > quoted_price:
            quoted_price = price

        if await self._orders.has_open_order_of_kind(user_id, OrderKind.TELEGRAM):
            raise DuplicateOperationError("a Telegram number purchase is already in flight")

        user = await self._users.get(user_id)
        if user is None or user.balance < quoted_price:
            raise InsufficientBalanceError(
                "balance too low", required=quoted_price, available=user.balance if user else 0
            )

        order = await self._orders.create(
            user_id=user_id,
            kind=OrderKind.TELEGRAM,
            status=OrderStatus.PENDING,
            provider=self._provider.name,
            service_code=PRODUCT_CODE,
            service_name=PRODUCT_NAME,
            country_name=country.name,
            # `link` is unused by this order kind (it's an SMM-only column);
            # reused here to keep the raw TG-Lion country code, since
            # `country_id` is typed for the numeric ids the other SMS
            # providers use and TG-Lion's codes ("in", "us", ...) are
            # strings. This is what makes "Buy Again" possible without
            # re-parsing the display name back into a code.
            link=country.code,
            price=quoted_price,
            provider_cost=live_cost,
        )
        change = await self._wallet.debit(
            user_id,
            quoted_price,
            TransactionType.PURCHASE,
            idempotency_key=f"purchase:order:{order.id}",
            reference=f"order #{order.id}",
            description=f"Telegram number — {country.name}",
        )
        await self._session.commit()

        try:
            number = await self._provider.create_number(country_code)
        except ProviderError:
            await self._refund_and_fail(order, "TG-Lion rejected the purchase")
            raise

        # The phone number itself is TG-Lion's only identifier -- it has no
        # separate opaque activation id the way TemporaSMS/SMS-Activate do.
        order.provider_order_id = number.number
        order.phone = number.number
        order.status = OrderStatus.PROCESSING
        order.expires_at = datetime.utcnow() + timedelta(seconds=self._settings.tg_lion_timeout)
        if number.cost:
            order.provider_cost = number.cost
        await self._session.commit()

        logger.info(
            "telegram_number.created",
            order_id=order.id,
            user_id=user_id,
            country=country_code,
            price=quoted_price,
        )
        return TelegramPurchase(order, change.balance_after)

    # -- lifecycle ------------------------------------------------------

    async def refresh(self, order: Order) -> Order:
        """Ask TG-Lion for the code right now. Never buys another number.

        A tap on Refresh and a background poll both land here, and both only
        ever call ``get_code`` -- there is no path from here back into
        :meth:`purchase`.
        """
        if self._provider is None or not order.provider_order_id:
            return order
        if OrderStatus(order.status).is_final:
            return order
        if order.expires_at and order.expires_at < datetime.utcnow():
            await self.expire(order)
            return order

        try:
            result = await self._provider.get_code(order.provider_order_id)
        except ProviderError as exc:
            logger.warning("telegram_number.poll_failed", order_id=order.id, error=str(exc))
            return order

        if result is not None:
            order.sms_code = result.code
            order.status = OrderStatus.SUCCESS
            order.completed_at = datetime.utcnow()
            await self._session.commit()
            logger.info("telegram_number.completed", order_id=order.id)
        return order

    async def cancel(self, order_id: int, user_id: int) -> Order:
        """Give up on a pending number and refund it.

        Purely local: TG-Lion exposes no release/cancel call in the reference
        implementation this adapter is built from, so there is nothing
        upstream to tell -- only our own refund obligation to honour.
        """
        order = await self.get_owned(order_id, user_id)
        if OrderStatus(order.status).is_final:
            raise DuplicateOperationError("order already closed")

        await self._refund_once(order, OrderStatus.CANCELLED, "cancelled by user")
        await self._session.commit()
        return order

    async def expire(self, order: Order) -> None:
        """Close a number that timed out without a code, refunding the user."""
        if OrderStatus(order.status).is_final:
            return
        await self._refund_once(order, OrderStatus.EXPIRED, "no code received in time")
        await self._session.commit()
        logger.info("telegram_number.expired", order_id=order.id)

    async def fail_orphan(self, order: Order) -> None:
        """Close an order that was charged for but never reached the provider."""
        if OrderStatus(order.status).is_final or order.provider_order_id:
            return
        await self._refund_once(order, OrderStatus.FAILED, "never reached the provider")
        await self._session.commit()
        logger.warning("telegram_number.orphan_refunded", order_id=order.id, user_id=order.user_id)

    # -- reads ------------------------------------------------------------

    async def get_owned(self, order_id: int, user_id: int) -> Order:
        order = await self._orders.get_owned(order_id, user_id)
        if order is None or OrderKind(order.kind) is not OrderKind.TELEGRAM:
            raise OrderNotFoundError(f"order {order_id}")
        return order

    async def open_orders(self):
        return await self._orders.list_open(OrderKind.TELEGRAM)

    # -- internals ------------------------------------------------------

    async def _refund_once(self, order: Order, status: OrderStatus, reason: str) -> None:
        if order.refunded_at is None:
            change = await self._wallet.refund(order.user_id, order.price, order.id, reason)
            if change.applied:
                order.refunded_at = datetime.utcnow()
        order.status = status

    async def _refund_and_fail(self, order: Order, reason: str) -> None:
        await self._refund_once(order, OrderStatus.FAILED, reason)
        await self._session.commit()
        logger.warning("telegram_number.purchase_failed", order_id=order.id, reason=reason)
