"""Service and country catalogue.

Provider metadata is slow-changing and expensive to fetch, so it is cached with
a TTL and searched in memory. Prices for a *specific* purchase are never served
from here -- :class:`~app.services.orders.OrderService` re-reads them live.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.countries import dial_code
from app.core.logging import get_logger
from app.providers.base import (
    BaseSMSProvider,
    CountryOffer,
    SmsCountry,
    SmsService,
)
from app.services.pricing import PricingService
from app.utils.cache import TTLCache

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PricedCountry:
    """A country with the *user-facing* price already computed."""

    country: SmsCountry
    price: int


@dataclass(frozen=True, slots=True)
class PricedOffer:
    """A service available in a country, with the *user-facing* price."""

    offer: CountryOffer
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
        self._all_countries = TTLCache(provider.get_all_countries, settings.cache_ttl_seconds)
        self._offers: dict[int, TTLCache[list[CountryOffer]]] = {}
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

    # -- country-first view -------------------------------------------------

    async def all_countries(self) -> list[PricedCountry]:
        """Every country, priced at its cheapest service. The opening screen."""
        return [
            PricedCountry(country, self._pricing.quote(country.cost).total)
            for country in await self._all_countries.get()
        ]

    async def search_all_countries(self, query: str) -> list[PricedCountry]:
        needle = query.lower().lstrip("+")
        return [
            priced
            for priced in await self.all_countries()
            if needle in priced.country.name.lower()
            or needle == str(priced.country.id)
            or needle in dial_code(priced.country.name).lstrip("+")
        ]

    async def find_any_country(self, country_id: int) -> PricedCountry | None:
        return next((p for p in await self.all_countries() if p.country.id == country_id), None)

    async def offers_in(self, country_id: int) -> list[PricedOffer]:
        """What can be bought in one country, priced for the user."""
        cache = self._offers.get(country_id)
        if cache is None:
            cache = TTLCache(
                lambda cid=country_id: self._provider.get_services_for(cid), self._ttl
            )
            self._offers[country_id] = cache
        return [
            PricedOffer(offer, self._pricing.quote(offer.cost).total) for offer in await cache.get()
        ]

    async def search_offers(self, country_id: int, query: str) -> list[PricedOffer]:
        needle = query.lower()
        return [
            priced
            for priced in await self.offers_in(country_id)
            if needle in priced.offer.service.name.lower()
            or needle in priced.offer.service.code.lower()
        ]

    async def find_offer(self, country_id: int, service_code: str) -> PricedOffer | None:
        return next(
            (p for p in await self.offers_in(country_id) if p.offer.service.code == service_code),
            None,
        )

    def invalidate(self) -> None:
        """Drop every cached catalogue. Used by the admin 'refresh' action."""
        self._services.invalidate()
        self._all_countries.invalidate()
        for cache in self._countries.values():
            cache.invalidate()
        for cache in self._offers.values():
            cache.invalidate()
