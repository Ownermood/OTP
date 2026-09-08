"""Generic SMM panel adapter.

Nearly every SMM panel exposes the same POST API that Perfect Panel
popularised: one endpoint, an ``action`` field, and an API key. This adapter
speaks that dialect, so pointing ``SMM_API_URL`` at a different panel is
usually all that is required.
"""

from __future__ import annotations

from decimal import Decimal

import httpx

from app.core.constants import SMM_CATEGORY_KEYWORDS, SmmCategory
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.core.money import round_up_minor
from app.providers.base import BaseSMMProvider, SmmOrderStatus, SmmService
from app.utils.http import request

logger = get_logger(__name__)

#: Panel status -> our vocabulary.
STATUS_MAP = {
    "pending": "pending",
    "in progress": "processing",
    "processing": "processing",
    "completed": "success",
    "partial": "partial",
    "canceled": "cancelled",
    "cancelled": "cancelled",
    "refunded": "cancelled",
    "error": "failed",
    "fail": "failed",
}


def classify(category: str, name: str) -> SmmCategory:
    """Bucket a panel's free-text category into one of our platform tabs."""
    haystack = f"{category} {name}".lower()
    for bucket, keywords in SMM_CATEGORY_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return bucket
    return SmmCategory.OTHER


class GenericSmmProvider(BaseSMMProvider):
    """Perfect-Panel-compatible SMM provider."""

    name = "generic"

    def __init__(
        self, api_url: str, api_key: str, currency_rate: Decimal, timeout: float = 20.0
    ) -> None:
        self._api_key = api_key
        self._url = api_url
        self._rate = currency_rate
        self._client = httpx.AsyncClient(timeout=timeout)

    async def get_services(self) -> list[SmmService]:
        payload = await self._call({"action": "services"})
        if not isinstance(payload, list):
            raise ProviderError("SMM panel did not return a service list")

        services: list[SmmService] = []
        for item in payload:
            try:
                services.append(
                    SmmService(
                        service_id=str(item["service"]),
                        name=str(item["name"]),
                        category=classify(str(item.get("category", "")), str(item["name"])).value,
                        rate_per_1000=round_up_minor(Decimal(str(item["rate"])) * self._rate),
                        min_quantity=int(item.get("min", 1)),
                        max_quantity=int(item.get("max", 1_000_000)),
                    )
                )
            except (KeyError, ValueError, TypeError):
                logger.warning("smm.malformed_service", raw=str(item)[:120])
        return services

    async def create_order(self, service_id: str, link: str, quantity: int) -> str:
        # retries=0: a retried create is a duplicate order the user pays for twice.
        payload = await self._call(
            {"action": "add", "service": service_id, "link": link, "quantity": quantity},
            retries=0,
        )
        order_id = payload.get("order") if isinstance(payload, dict) else None
        if not order_id:
            raise ProviderError(str(payload.get("error", "SMM order rejected"))[:120])
        return str(order_id)

    async def get_order_status(self, provider_order_id: str) -> SmmOrderStatus:
        payload = await self._call({"action": "status", "order": provider_order_id})
        if not isinstance(payload, dict) or payload.get("status") is None:
            return SmmOrderStatus(state="processing")
        return SmmOrderStatus(
            state=STATUS_MAP.get(str(payload.get("status", "")).lower(), "processing"),
            start_count=_as_int(payload.get("start_count")),
            remains=_as_int(payload.get("remains")),
        )

    async def get_balance(self) -> int:
        payload = await self._call({"action": "balance"})
        if not isinstance(payload, dict):
            return 0
        return round_up_minor(Decimal(str(payload.get("balance", 0))) * self._rate)

    async def close(self) -> None:
        await self._client.aclose()

    async def _call(self, data: dict[str, object], retries: int = 2):
        response = await request(
            self._client,
            "POST",
            self._url,
            provider="smm",
            data={"key": self._api_key, **data},
            retries=retries,
        )
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(f"SMM panel returned non-JSON: {response.text[:80]}") from exc


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
