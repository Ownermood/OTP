"""TG-Lion adapter: Telegram-capable numbers, for the dedicated Telegram flow.

TG-Lion is *not* a service-verification provider like TemporaSMS or
SMS-Activate -- it has no notion of "which service" (WhatsApp, Instagram, ...)
at all. It sells raw numbers by country, and the "OTP" is that number's own
Telegram login code. That is a different product, so this adapter does not
implement :class:`app.providers.base.BaseSMSProvider` -- doing so would mean
inventing a fake ``service_code`` to satisfy an interface that does not
describe what TG-Lion actually does. It only implements
:class:`app.providers.base.BaseProvider` (balance + health-check), plus its
own three real operations: list countries, buy a number, ask for its code.

Every response is treated as untrusted input: a non-200, a non-JSON body, or
a JSON body missing the fields we need all raise :class:`ProviderError`
rather than propagating a ``KeyError``/``TypeError`` into a handler.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

from app.core.exceptions import ProviderAuthError, ProviderError
from app.core.logging import get_logger
from app.core.money import round_up_minor
from app.providers.base import BaseProvider
from app.utils.http import request

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TgLionCountry:
    """One country TG-Lion sells numbers for."""

    code: str
    name: str
    #: Cost in minor units of *our* currency, already converted.
    cost: int
    available: int | None = None


@dataclass(frozen=True, slots=True)
class TgLionNumber:
    """A freshly purchased Telegram number."""

    number: str
    #: Cost actually charged, in minor units of our currency.
    cost: int = 0


@dataclass(frozen=True, slots=True)
class TgLionCode:
    """One ``getCode`` poll result. ``None`` from :meth:`get_code` means "not yet"."""

    code: str
    password: str | None = None


class TgLionProvider(BaseProvider):
    """Adapter for https://TG-Lion.net."""

    name = "tg_lion"

    def __init__(
        self,
        api_key: str,
        your_id: str,
        base_url: str,
        currency_rate: Decimal,
        timeout: float = 20.0,
        retries: int = 2,
    ) -> None:
        self._api_key = api_key
        self._your_id = your_id
        self._rate = currency_rate
        self._retries = retries
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    # -- catalogue --------------------------------------------------------

    async def get_countries(self) -> list[TgLionCountry]:
        payload = await self._get("available_countries", retries=self._retries)
        countries_raw = payload.get("countries")
        if not isinstance(countries_raw, dict):
            raise ProviderError("tg_lion: available_countries returned no countries")

        countries: list[TgLionCountry] = []
        for raw_code, info in countries_raw.items():
            if not isinstance(info, dict):
                continue
            code = str(raw_code).strip().lower()
            if not code:
                continue
            cost = self._to_minor(info.get("price"))
            if cost is None:
                continue
            countries.append(
                TgLionCountry(
                    code=code,
                    name=str(info.get("name") or code.upper()),
                    cost=cost,
                    available=_as_int(
                        info.get("stock") or info.get("count") or info.get("quantity")
                    ),
                )
            )
        countries.sort(key=lambda country: country.name)
        return countries

    async def get_price(self, country_code: str) -> int:
        payload = await self._get(
            "country_info", country_code=country_code, retries=self._retries
        )
        cost = self._to_minor(payload.get("price"))
        if cost is None:
            raise ProviderError(f"tg_lion: no price for country {country_code!r}")
        return cost

    # -- numbers ------------------------------------------------------------

    async def create_number(self, country_code: str) -> TgLionNumber:
        # retries=0: a retried purchase can leave an orphaned paid number behind.
        payload = await self._get("getNumber", country_code=country_code, retries=0)
        number = payload.get("Number") or payload.get("number")
        if not number:
            raise ProviderError("tg_lion: getNumber did not return a number")
        return TgLionNumber(number=str(number))

    async def get_code(self, number: str) -> TgLionCode | None:
        """Ask for the current code. ``None`` means "nothing yet", not an error."""
        payload = await self._get("getCode", number=number, retries=self._retries)
        code = payload.get("code") or payload.get("otp")
        if not code:
            return None
        password = payload.get("pass")
        return TgLionCode(code=str(code), password=str(password) if password else None)

    # -- account ------------------------------------------------------------

    async def get_balance(self) -> int:
        payload = await self._get("get_balance", retries=self._retries)
        cost = self._to_minor(payload.get("balance"))
        return cost or 0

    async def close(self) -> None:
        await self._client.aclose()

    # -- internals ------------------------------------------------------

    async def _get(self, action: str, *, retries: int, **params: object) -> dict:
        """GET one action. Never trusts the body's shape blindly.

        TG-Lion answers everything with HTTP 200 (even its own errors), so
        the only signal that a call failed is ``status`` inside the JSON
        body -- there is no HTTP status code to lean on the way
        :func:`app.utils.http.request` normally does for auth/rate-limit.
        """
        query = {
            "action": action,
            "apiKey": self._api_key,
            "YourID": self._your_id,
            **params,
        }
        response = await request(
            self._client, "GET", "", provider=self.name, params=query, retries=retries
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(f"tg_lion returned non-JSON for {action!r}") from exc
        if not isinstance(body, dict):
            raise ProviderError(f"tg_lion returned an unexpected shape for {action!r}")

        status = str(body.get("status", "")).lower()
        if status not in ("ok", "success", "true", "1"):
            message = body.get("message") or body.get("error") or status or "unknown error"
            if "key" in str(message).lower() or "auth" in str(message).lower():
                raise ProviderAuthError(f"tg_lion rejected our credentials: {message}")
            raise ProviderError(f"tg_lion {action}: {message}")
        return body

    def _to_minor(self, value: object) -> int | None:
        try:
            price = Decimal(str(value))
        except (InvalidOperation, TypeError):
            return None
        return round_up_minor(price * self._rate)


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
