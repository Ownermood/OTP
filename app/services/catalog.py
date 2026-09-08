"""Service and country catalogue.

Provider metadata is slow-changing and expensive to fetch, so it is cached with
a TTL and searched in memory. Prices for a *specific* purchase are never served
from here -- :class:`~app.services.orders.OrderService` re-reads them live.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.logging import get_logger
from app.providers.base import BaseSMSProvider, SmsCountry, SmsService
from app.services.pricing import PricingService
from app.utils.cache import TTLCache

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PricedCountry:
    """A country with the *user-facing* price already computed."""

    country: SmsCountry
    price: int


class CatalogService:
    """Cached, searchable view of what the SMS provider offers."""

    def __init__(
        self, provider: BaseSMSProvider, pricing: PricingService, settings: Settings
    ) -> None:
        self._provider = provider
        self._pricing = pricing
        self._services = TTLCache(provider.get_services, settings.cache_ttl_seconds)
        self._countries: dict[str, TTLCache[list[SmsCountry]]] = {}
        self._ttl = settings.cache_ttl_seconds

    async def services(self) -> list[SmsService]:
        return await self._services.get()

    async def find_service(self, code: str) -> SmsService | None:
        return next((s for s in await self.services() if s.code == code), None)

    async def search_services(self, query: str) -> list[SmsService]:
        """Case-insensitive partial match on name or provider code.

        Exact code matches and prefix matches rank above substring matches, so
        typing ``whats`` puts WhatsApp first rather than somewhere in a list.
        """
        needle = query.lower()
        exact, prefix, contains = [], [], []
        for service in await self.services():
            name = service.name.lower()
            code = service.code.lower()
            if code == needle or name == needle:
                exact.append(service)
            elif name.startswith(needle) or code.startswith(needle):
                prefix.append(service)
            elif needle in name or needle in code:
                contains.append(service)
        return exact + prefix + contains

    async def countries(self, service_code: str) -> list[PricedCountry]:
        """Countries offering a service, priced for the user."""
        cache = self._countries.get(service_code)
        if cache is None:
            cache = TTLCache(
                lambda code=service_code: self._provider.get_countries(code), self._ttl
            )
            self._countries[service_code] = cache
        countries = await cache.get()
        return [
            PricedCountry(country, self._pricing.quote(country.cost).total)
            for country in countries
        ]

    async def search_countries(self, service_code: str, query: str) -> list[PricedCountry]:
        needle = query.lower()
        return [
            priced
            for priced in await self.countries(service_code)
            if needle in priced.country.name.lower() or needle == str(priced.country.id)
        ]

    async def find_country(self, service_code: str, country_id: int) -> PricedCountry | None:
        return next(
            (p for p in await self.countries(service_code) if p.country.id == country_id), None
        )

    def invalidate(self) -> None:
        """Drop every cached catalogue. Used by the admin 'refresh' action."""
        self._services.invalidate()
        for cache in self._countries.values():
            cache.invalidate()
