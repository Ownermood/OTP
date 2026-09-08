"""SMS-Activate adapter.

Everything specific to SMS-Activate's ``handler_api.php`` protocol -- its
colon-delimited responses, its numeric status codes, its currency -- is
confined to this file.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import httpx

from app.core.exceptions import (
    InsufficientProviderBalanceError,
    NoNumbersAvailableError,
    ProviderAuthError,
    ProviderError,
)
from app.core.logging import get_logger
from app.core.money import round_up_minor
from app.providers.base import (
    Activation,
    ActivationStatus,
    BaseSMSProvider,
    SmsCountry,
    SmsService,
)
from app.utils.http import request

logger = get_logger(__name__)

API_PATH = "stubs/handler_api.php"

#: Provider error strings that mean "try a different service/country".
NO_NUMBERS_ERRORS = frozenset({"NO_NUMBERS", "NO_BALANCE_FORWARD_OPERATOR", "OPERATORS_NOT_FOUND"})
AUTH_ERRORS = frozenset({"BAD_KEY", "ERROR_SQL", "BANNED"})

#: setStatus codes.
STATUS_CANCEL = 8
STATUS_FINISH = 6


class SmsActivateProvider(BaseSMSProvider):
    """Adapter for https://sms-activate.guru."""

    name = "sms_activate"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        currency_rate: Decimal,
        timeout: float = 20.0,
        retries: int = 2,
    ) -> None:
        self._api_key = api_key
        self._rate = currency_rate
        self._retries = retries
        self._client = httpx.AsyncClient(
            base_url=base_url,
            params={"api_key": api_key},
            timeout=timeout,
        )

    # -- catalogue ------------------------------------------------------

    async def get_services(self) -> list[SmsService]:
        payload = await self._json({"action": "getServicesList", "lang": "en"})
        services = payload.get("services", []) if isinstance(payload, dict) else []
        return [
            SmsService(code=item["code"], name=item.get("name") or item["code"])
            for item in services
            if item.get("code")
        ]

    async def get_countries(self, service_code: str) -> list[SmsCountry]:
        payload = await self._json(
            {"action": "getTopCountriesByService", "service": service_code}
        )
        if not isinstance(payload, dict):
            return []

        countries: list[SmsCountry] = []
        for entry in payload.values():
            country_id = entry.get("country")
            if country_id is None:
                continue
            countries.append(
                SmsCountry(
                    id=int(country_id),
                    name=str(entry.get("country_name") or country_id),
                    cost=self._to_minor(entry.get("price", 0)),
                    available=_as_int(entry.get("count")),
                )
            )
        countries.sort(key=lambda country: country.cost)
        return countries

    async def get_price(self, service_code: str, country_id: int) -> int:
        payload = await self._json(
            {"action": "getPrices", "service": service_code, "country": country_id}
        )
        try:
            entry = payload[str(country_id)][service_code]
        except (KeyError, TypeError) as exc:
            raise NoNumbersAvailableError(
                f"no price for {service_code}/{country_id}"
            ) from exc
        return self._to_minor(entry["cost"])

    # -- activations ----------------------------------------------------

    async def create_activation(self, service_code: str, country_id: int) -> Activation:
        # retries=0: a retried purchase can leave an orphaned paid number behind.
        text = await self._text(
            {"action": "getNumber", "service": service_code, "country": country_id},
            retries=0,
        )
        if not text.startswith("ACCESS_NUMBER"):
            raise self._map_error(text)

        _, provider_order_id, phone = text.split(":", 2)
        return Activation(
            provider_order_id=provider_order_id,
            phone=phone,
            cost=await self._safe_price(service_code, country_id),
            expires_at=datetime.utcnow() + timedelta(minutes=20),
        )

    async def get_activation_status(self, provider_order_id: str) -> ActivationStatus:
        text = await self._text({"action": "getStatus", "id": provider_order_id})
        if text.startswith("STATUS_OK"):
            code = text.split(":", 1)[1] if ":" in text else None
            return ActivationStatus(state="received", code=code, text=code)
        if text == "STATUS_CANCEL":
            return ActivationStatus(state="cancelled")
        if text in ("STATUS_WAIT_CODE", "STATUS_WAIT_RETRY", "STATUS_WAIT_RESEND"):
            return ActivationStatus(state="waiting")
        if text == "NO_ACTIVATION":
            return ActivationStatus(state="expired")
        logger.warning("sms_activate.unknown_status", status=text, order=provider_order_id)
        return ActivationStatus(state="waiting")

    async def cancel_activation(self, provider_order_id: str) -> bool:
        text = await self._text(
            {"action": "setStatus", "id": provider_order_id, "status": STATUS_CANCEL}
        )
        return text in ("ACCESS_CANCEL", "ACCESS_READY")

    async def finish_activation(self, provider_order_id: str) -> bool:
        text = await self._text(
            {"action": "setStatus", "id": provider_order_id, "status": STATUS_FINISH}
        )
        return text == "ACCESS_ACTIVATION"

    # -- account --------------------------------------------------------

    async def get_balance(self) -> int:
        text = await self._text({"action": "getBalance"})
        if not text.startswith("ACCESS_BALANCE"):
            raise self._map_error(text)
        return self._to_minor(text.split(":", 1)[1])

    async def close(self) -> None:
        await self._client.aclose()

    # -- internals ------------------------------------------------------

    async def _text(self, params: dict[str, object], retries: int | None = None) -> str:
        response = await request(
            self._client,
            "GET",
            API_PATH,
            provider=self.name,
            params=params,
            retries=self._retries if retries is None else retries,
        )
        return response.text.strip()

    async def _json(self, params: dict[str, object], retries: int | None = None) -> dict:
        response = await request(
            self._client,
            "GET",
            API_PATH,
            provider=self.name,
            params=params,
            retries=self._retries if retries is None else retries,
        )
        body = response.text.strip()
        if body.startswith(("BAD_", "NO_", "ERROR", "WRONG")):
            raise self._map_error(body)
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(f"{self.name} returned non-JSON: {body[:80]}") from exc

    async def _safe_price(self, service_code: str, country_id: int) -> int:
        """Best-effort cost lookup -- a purchase must not fail over a price probe."""
        try:
            return await self.get_price(service_code, country_id)
        except ProviderError:
            return 0

    def _to_minor(self, value: object) -> int:
        """Convert a provider-currency amount into our currency's minor units."""
        return round_up_minor(Decimal(str(value)) * self._rate)

    def _map_error(self, text: str) -> ProviderError:
        code = text.split(":", 1)[0].strip().upper()
        if code in NO_NUMBERS_ERRORS:
            return NoNumbersAvailableError(code)
        if code in AUTH_ERRORS:
            return ProviderAuthError(code)
        if code in ("NO_BALANCE", "BALANCE_LOW"):
            return InsufficientProviderBalanceError(code)
        return ProviderError(text[:120])


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
