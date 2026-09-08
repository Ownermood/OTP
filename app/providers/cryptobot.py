"""CryptoBot (@CryptoBot / pay.crypt.bot) deposit adapter."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import httpx

from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.core.money import to_major
from app.providers.base import BasePaymentProvider, Invoice
from app.utils.http import request

logger = get_logger(__name__)

#: CryptoBot status -> our PaymentStatus vocabulary.
STATUS_MAP = {"active": "pending", "paid": "paid", "expired": "expired"}


class CryptoBotProvider(BasePaymentProvider):
    """Crypto deposits via the Crypto Pay API."""

    name = "cryptobot"

    def __init__(
        self,
        api_token: str,
        base_url: str,
        asset: str,
        rate: Decimal,
        timeout_minutes: int,
        timeout: float = 20.0,
    ) -> None:
        self._asset = asset
        self._rate = rate
        self._timeout_minutes = timeout_minutes
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Crypto-Pay-API-Token": api_token},
            timeout=timeout,
        )

    async def create_invoice(self, user_id: int, amount: int, description: str) -> Invoice:
        crypto_amount = self._to_crypto(amount)
        # retries=0: a retried create leaves a second unpaid invoice behind.
        payload = await self._call(
            "createInvoice",
            {
                "asset": self._asset,
                "amount": str(crypto_amount),
                "description": description,
                "payload": str(user_id),
                "expires_in": self._timeout_minutes * 60,
            },
            retries=0,
        )
        return Invoice(
            invoice_id=str(payload["invoice_id"]),
            pay_url=payload.get("bot_invoice_url") or payload["pay_url"],
            provider_amount=f"{crypto_amount} {self._asset}",
            expires_at=datetime.utcnow() + timedelta(minutes=self._timeout_minutes),
        )

    async def check_payment(self, invoice_id: str) -> str:
        payload = await self._call("getInvoices", {"invoice_ids": invoice_id})
        items = payload.get("items", [])
        if not items:
            return "failed"
        return STATUS_MAP.get(items[0].get("status", ""), "pending")

    async def check_many(self, invoice_ids: list[str]) -> dict[str, str]:
        """Poll several invoices in one call -- what the payment worker uses."""
        if not invoice_ids:
            return {}
        payload = await self._call("getInvoices", {"invoice_ids": ",".join(invoice_ids)})
        return {
            str(item["invoice_id"]): STATUS_MAP.get(item.get("status", ""), "pending")
            for item in payload.get("items", [])
        }

    async def cancel_invoice(self, invoice_id: str) -> bool:
        try:
            await self._call("deleteInvoice", {"invoice_id": invoice_id}, retries=0)
            return True
        except ProviderError:
            return False

    async def get_balance(self) -> int:
        payload = await self._call("getBalance", {})
        for item in payload:
            if item.get("currency_code") == self._asset:
                return int(Decimal(item["available"]) * self._rate * 100)
        return 0

    async def close(self) -> None:
        await self._client.aclose()

    def _to_crypto(self, minor: int) -> Decimal:
        """Convert our minor units into the crypto asset amount."""
        return (to_major(minor) / self._rate).quantize(Decimal("0.000001"))

    async def _call(self, method: str, params: dict[str, object], retries: int = 2):
        response = await request(
            self._client, "GET", method, provider=self.name, params=params, retries=retries
        )
        body = response.json()
        if not body.get("ok"):
            error = body.get("error", {})
            raise ProviderError(f"cryptobot: {error.get('name', 'unknown error')}")
        return body["result"]
