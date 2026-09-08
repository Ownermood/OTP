"""TemporaSMS adapter.

TemporaSMS speaks a *variant* of the SMS-Activate protocol at the same
``handler_api.php`` endpoint, so the activation half of the protocol is
inherited unchanged. The catalogue half differs in three ways, and each one
is handled below:

1. Every catalogue call requires an ``operator`` parameter. Omitting it
   answers ``BAD_OPERATOR``; the operator list comes from ``getOperators``.
2. ``getServicesList`` and ``getTopCountriesByService`` answer ``BAD_ACTION``.
   The only catalogue source is ``getPrices``, which returns prices *per
   country*, so the whole catalogue is fetched once and cached rather than
   queried per service.
3. A ``getPrices`` entry maps price to stock (``{"0.42": 118}``) instead of
   carrying ``cost``/``count`` keys, and one service can be offered at
   several price tiers. We quote the cheapest tier that actually has stock,
   because that is the tier a purchase will draw from.

Because the catalogue arrives keyed by country, refreshing it is one request
when the provider accepts a country-less ``getPrices`` and one request per
country otherwise. Either way it happens on a TTL, never per button press.
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal, InvalidOperation

from app.core.exceptions import NoNumbersAvailableError, ProviderError
from app.core.logging import get_logger
from app.providers.base import Activation, SmsCountry, SmsService
from app.providers.service_names import service_name
from app.providers.sms_activate import SmsActivateProvider

logger = get_logger(__name__)

#: How long a fetched catalogue stays usable before the next refresh.
CATALOGUE_TTL_SECONDS = 300.0

#: Concurrent per-country price requests when a bulk fetch is unavailable.
_FANOUT = 8

#: cost in minor units, stock (``None`` when the provider does not say).
Offer = tuple[int, int | None]


class TemporaSmsProvider(SmsActivateProvider):
    """Adapter for https://api.temporasms.com."""

    name = "temporasms"

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._operator: str | None = None
        self._catalogue: dict[int, dict[str, Offer]] = {}
        self._country_names: dict[int, str] = {}
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    # -- catalogue ------------------------------------------------------

    async def get_services(self) -> list[SmsService]:
        catalogue = await self._load()
        codes = {code for offers in catalogue.values() for code in offers}
        services = [SmsService(code=code, name=service_name(code)) for code in codes]
        services.sort(key=lambda service: service.name)
        return services

    async def get_countries(self, service_code: str) -> list[SmsCountry]:
        catalogue = await self._load()
        countries = [
            SmsCountry(
                id=country_id,
                name=self._country_names.get(country_id, str(country_id)),
                cost=offer[0],
                available=offer[1],
            )
            for country_id, offers in catalogue.items()
            if (offer := offers.get(service_code)) is not None
        ]
        countries.sort(key=lambda country: country.cost)
        return countries

    async def get_price(self, service_code: str, country_id: int) -> int:
        catalogue = await self._load()
        offer = catalogue.get(country_id, {}).get(service_code)
        if offer is None:
            # A price we have never seen may simply predate the last refresh.
            offer = (await self._fetch_country(country_id)).get(service_code)
        if offer is None:
            raise NoNumbersAvailableError(f"no price for {service_code}/{country_id}")
        return offer[0]

    # -- activations ----------------------------------------------------

    async def create_activation(self, service_code: str, country_id: int) -> Activation:
        # retries=0: a retried purchase can leave an orphaned paid number behind.
        text = await self._text(
            {
                "action": "getNumber",
                "service": service_code,
                "country": country_id,
                "operator": await self._operator_id(),
            },
            retries=0,
        )
        if not text.startswith("ACCESS_NUMBER"):
            raise self._map_error(text)

        _, provider_order_id, phone = text.split(":", 2)
        return Activation(
            provider_order_id=provider_order_id,
            phone=phone,
            cost=await self._safe_price(service_code, country_id),
            expires_at=self._default_expiry(),
        )

    # -- internals ------------------------------------------------------

    async def _operator_id(self) -> str:
        """The operator every catalogue call must carry."""
        if self._operator is not None:
            return self._operator

        try:
            payload = await self._json({"action": "getOperators"})
        except ProviderError:
            payload = {}

        # ``{"OPERATOR 1": "1", "OPERATOR 2": "2"}`` -- ids are the values.
        ids = [str(value) for value in payload.values() if str(value).strip()]
        if not ids and isinstance(payload, dict):
            ids = [str(key) for key in payload]
        self._operator = ids[0] if ids else "1"
        return self._operator

    async def _load(self) -> dict[int, dict[str, Offer]]:
        """Return the cached catalogue, refreshing it when the TTL has passed."""
        if self._catalogue and time.monotonic() - self._fetched_at < CATALOGUE_TTL_SECONDS:
            return self._catalogue

        async with self._lock:
            # A second waiter arrives with the refresh already done.
            if self._catalogue and time.monotonic() - self._fetched_at < CATALOGUE_TTL_SECONDS:
                return self._catalogue
            try:
                catalogue = await self._fetch_catalogue()
            except ProviderError:
                if self._catalogue:
                    # A stale catalogue beats an empty menu; log and keep serving.
                    logger.warning("temporasms.catalogue_refresh_failed", exc_info=True)
                    return self._catalogue
                raise
            self._catalogue = catalogue
            self._fetched_at = time.monotonic()
            return self._catalogue

    async def _fetch_catalogue(self) -> dict[int, dict[str, Offer]]:
        await self._load_country_names()

        # Preferred: one request for every country.
        try:
            payload = await self._json(
                {"action": "getPrices", "operator": await self._operator_id()}
            )
        except ProviderError:
            payload = {}
        catalogue = self._parse_prices(payload)
        if len(catalogue) > 1:
            return catalogue

        # Fallback: the provider only prices one country at a time.
        country_ids = list(self._country_names) or list(catalogue)
        if not country_ids:
            raise ProviderError("temporasms returned no countries")

        semaphore = asyncio.Semaphore(_FANOUT)

        async def one(country_id: int) -> tuple[int, dict[str, Offer]]:
            async with semaphore:
                return country_id, await self._fetch_country(country_id)

        results = await asyncio.gather(
            *(one(country_id) for country_id in country_ids), return_exceptions=True
        )
        merged: dict[int, dict[str, Offer]] = {}
        for result in results:
            if isinstance(result, BaseException):
                continue  # One unlucky country must not blank the whole menu.
            country_id, offers = result
            if offers:
                merged[country_id] = offers
        if not merged:
            raise ProviderError("temporasms priced no countries")
        return merged

    async def _fetch_country(self, country_id: int) -> dict[str, Offer]:
        try:
            payload = await self._json(
                {
                    "action": "getPrices",
                    "country": country_id,
                    "operator": await self._operator_id(),
                }
            )
        except ProviderError:
            return {}
        return self._parse_prices(payload).get(country_id, {})

    async def _load_country_names(self) -> None:
        try:
            payload = await self._json(
                {"action": "getCountries", "operator": await self._operator_id()}
            )
        except ProviderError:
            return
        if isinstance(payload, dict):
            entries: list[object] = list(payload.values())
            keys: list[object] = list(payload)
        elif isinstance(payload, list):
            entries, keys = list(payload), []
        else:
            return

        for index, entry in enumerate(entries):
            key = keys[index] if keys else None
            if isinstance(entry, dict):
                country_id = _as_int(entry.get("id", key))
                name = entry.get("eng") or entry.get("name") or entry.get("rus")
            else:
                country_id = _as_int(key)
                name = entry
            if country_id is not None and name:
                self._country_names[country_id] = str(name).title()

    def _parse_prices(self, payload: object) -> dict[int, dict[str, Offer]]:
        """Parse ``{"<country>": {"<service>": <entry>}}`` into offers."""
        if not isinstance(payload, dict):
            return {}
        catalogue: dict[int, dict[str, Offer]] = {}
        for country_key, services in payload.items():
            country_id = _as_int(country_key)
            if country_id is None or not isinstance(services, dict):
                continue
            offers = {
                str(code): offer
                for code, entry in services.items()
                if (offer := self._to_offer(entry)) is not None
            }
            if offers:
                catalogue[country_id] = offers
        return catalogue

    def _to_offer(self, entry: object) -> Offer | None:
        """Turn one ``getPrices`` service entry into a quotable offer."""
        if isinstance(entry, (int, float, str)):
            price = _as_decimal(entry)
            return (self._to_minor(price), None) if price is not None else None
        if not isinstance(entry, dict):
            return None

        # SMS-Activate shape.
        if "cost" in entry:
            price = _as_decimal(entry["cost"])
            if price is None:
                return None
            return self._to_minor(price), _as_int(entry.get("count"))

        # TemporaSMS shape: ``{"<price>": <stock>}``, one key per tier.
        tiers = [
            (price, stock)
            for key, value in entry.items()
            if (price := _as_decimal(key)) is not None and (stock := _as_int(value)) is not None
        ]
        in_stock = [tier for tier in tiers if tier[1] > 0]
        if not in_stock:
            return None
        cheapest = min(in_stock, key=lambda tier: tier[0])
        return self._to_minor(cheapest[0]), sum(stock for _, stock in in_stock)


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
