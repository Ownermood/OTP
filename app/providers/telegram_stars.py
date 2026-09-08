"""Telegram Stars deposit adapter.

Stars checkout happens inside Telegram, so there is no upstream API to poll:
the invoice is a local record and ``successful_payment`` in the bot is what
settles it. ``check_payment`` therefore always answers ``pending`` and the
payment handler does the crediting.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, Decimal

from app.core.money import to_major
from app.providers.base import BasePaymentProvider, Invoice


class TelegramStarsProvider(BasePaymentProvider):
    """Deposits paid in Telegram Stars (XTR)."""

    name = "telegram_stars"
    supports_polling = False
    is_native = True

    def __init__(self, rate: Decimal, max_stars: int, timeout_minutes: int) -> None:
        self._rate = rate
        self._max_stars = max_stars
        self._timeout_minutes = timeout_minutes

    def stars_for(self, minor: int) -> int:
        """How many Stars ``minor`` units cost, always rounded up."""
        stars = (to_major(minor) / self._rate).quantize(Decimal("1"), rounding=ROUND_CEILING)
        return int(stars)

    @property
    def max_stars(self) -> int:
        return self._max_stars

    async def create_invoice(self, user_id: int, amount: int, description: str) -> Invoice:
        stars = self.stars_for(amount)
        # The payload is the invoice id; Telegram echoes it back on success,
        # which is what makes settlement idempotent.
        return Invoice(
            invoice_id=uuid.uuid4().hex,
            pay_url="",
            provider_amount=str(stars),
            expires_at=datetime.utcnow() + timedelta(minutes=self._timeout_minutes),
        )

    async def check_payment(self, invoice_id: str) -> str:
        return "pending"

    async def get_balance(self) -> int:
        # Telegram holds the balance; nothing for us to report.
        return 0

    async def health_check(self) -> bool:
        return True
