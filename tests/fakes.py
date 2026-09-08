"""In-memory provider doubles."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.core.exceptions import NoNumbersAvailableError, ProviderError
from app.providers.base import (
    Activation,
    ActivationStatus,
    BasePaymentProvider,
    BaseSMMProvider,
    BaseSMSProvider,
    Invoice,
    Rental,
    SmmOrderStatus,
    SmmService,
    SmsCountry,
    SmsService,
)


class FakeSmsProvider(BaseSMSProvider):
    """A scriptable SMS provider."""

    name = "fake_sms"
    supports_rental = True

    def __init__(self, cost: int = 1_000) -> None:
        self.cost = cost
        self.created = 0
        self.cancelled: list[str] = []
        self.finished: list[str] = []
        self.fail_next = False
        self.status = ActivationStatus(state="waiting")

    async def get_services(self):
        return [SmsService(code="wa", name="WhatsApp", available=120)]

    async def get_countries(self, service_code: str):
        return [SmsCountry(id=22, name="India", cost=self.cost, available=120)]

    async def get_price(self, service_code: str, country_id: int) -> int:
        return self.cost

    async def create_activation(self, service_code: str, country_id: int) -> Activation:
        if self.fail_next:
            raise NoNumbersAvailableError("NO_NUMBERS")
        self.created += 1
        return Activation(
            provider_order_id=f"prov-{self.created}",
            phone=f"+9198765432{self.created:02d}",
            cost=self.cost,
            expires_at=datetime.utcnow() + timedelta(minutes=20),
        )

    async def get_activation_status(self, provider_order_id: str) -> ActivationStatus:
        return self.status

    async def cancel_activation(self, provider_order_id: str) -> bool:
        self.cancelled.append(provider_order_id)
        return True

    async def finish_activation(self, provider_order_id: str) -> bool:
        self.finished.append(provider_order_id)
        return True

    async def create_rental(self, service_code: str, country_id: int, hours: int) -> Rental:
        if self.fail_next:
            raise ProviderError("rental unavailable")
        self.created += 1
        return Rental(
            provider_order_id=f"rent-{self.created}",
            phone="+919876500000",
            cost=self.cost,
            expires_at=datetime.utcnow() + timedelta(hours=hours),
        )

    async def get_balance(self) -> int:
        return 500_000


class FakePaymentProvider(BasePaymentProvider):
    """A payment gateway whose invoice status the test controls."""

    name = "fake_pay"

    def __init__(self) -> None:
        self.status = "pending"
        self.created = 0

    async def create_invoice(self, user_id: int, amount: int, description: str) -> Invoice:
        self.created += 1
        return Invoice(
            invoice_id=f"inv-{self.created}",
            pay_url="https://example.test/pay",
            provider_amount="1.00",
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        )

    async def check_payment(self, invoice_id: str) -> str:
        return self.status

    async def get_balance(self) -> int:
        return 0


class FakeSmmProvider(BaseSMMProvider):
    name = "fake_smm"

    def __init__(self) -> None:
        self.created = 0
        self.fail_next = False
        self.status = SmmOrderStatus(state="processing", start_count=10, remains=90)

    async def get_services(self):
        return [
            SmmService(
                service_id="101",
                name="Instagram Followers",
                category="instagram",
                rate_per_1000=10_000,
                min_quantity=100,
                max_quantity=10_000,
            )
        ]

    async def create_order(self, service_id: str, link: str, quantity: int) -> str:
        if self.fail_next:
            raise ProviderError("panel rejected")
        self.created += 1
        return f"smm-{self.created}"

    async def get_order_status(self, provider_order_id: str) -> SmmOrderStatus:
        return self.status

    async def get_balance(self) -> int:
        return 100_000
