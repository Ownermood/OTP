"""Provider interfaces.

Every external integration is reached through one of these ABCs. Handlers and
services depend on the interface only, so swapping ``SMS_PROVIDER`` or adding a
payment gateway means adding one file and one registry entry -- never editing a
handler.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

# --------------------------------------------------------------------------
# Value objects. Providers translate their own wire formats into these, so
# nothing provider-shaped leaks past the adapter boundary.
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SmsService:
    """One verification service, e.g. WhatsApp."""

    code: str
    name: str
    #: How many numbers the provider claims to have, when it tells us.
    available: int | None = None


@dataclass(frozen=True, slots=True)
class SmsCountry:
    """One country offering a service, with the provider's own cost."""

    id: int
    name: str
    flag: str = ""
    #: Provider cost in *minor units of our currency*, already converted.
    cost: int = 0
    available: int | None = None


@dataclass(frozen=True, slots=True)
class Activation:
    """A freshly purchased number."""

    provider_order_id: str
    phone: str
    #: Provider cost actually charged, in minor units of our currency.
    cost: int = 0
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ActivationStatus:
    """Poll result for an activation."""

    #: One of: waiting, received, cancelled, expired.
    state: str
    code: str | None = None
    text: str | None = None


@dataclass(frozen=True, slots=True)
class Rental:
    """A rented number."""

    provider_order_id: str
    phone: str
    cost: int = 0
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RentalOffer:
    """One rentable service, priced for a specific country and duration.

    Providers quote rentals per (country, duration) pair rather than per hour,
    so the duration is chosen before the price is known.
    """

    code: str
    name: str
    #: Provider cost for the whole rental period, in minor units of our currency.
    cost: int
    available: int | None = None


@dataclass(frozen=True, slots=True)
class RentalMessage:
    """One SMS delivered to a rented number."""

    sender: str
    text: str
    received_at: str


@dataclass(frozen=True, slots=True)
class Invoice:
    """A deposit invoice created upstream."""

    invoice_id: str
    pay_url: str
    #: Amount in the provider's own unit (crypto amount, star count, ...).
    provider_amount: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class SmmService:
    """One SMM panel service."""

    service_id: str
    name: str
    category: str
    #: Provider rate per 1000 units, in minor units of our currency.
    rate_per_1000: int
    min_quantity: int
    max_quantity: int


@dataclass(frozen=True, slots=True)
class SmmOrderStatus:
    """Poll result for an SMM order."""

    #: One of: pending, processing, success, partial, cancelled, failed.
    state: str
    start_count: int | None = None
    remains: int | None = None


# --------------------------------------------------------------------------
# Interfaces
# --------------------------------------------------------------------------


class BaseProvider(ABC):
    """Shared lifecycle for every provider."""

    #: Stable identifier persisted on orders and payments. Never change it.
    name: str = "base"

    @abstractmethod
    async def get_balance(self) -> int:
        """Return our account balance with this provider, in minor units."""

    async def health_check(self) -> bool:
        """True when the provider answers. Used by the admin health screen."""
        try:
            await self.get_balance()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Release network resources. No-op for providers that hold none."""
        return None


class BaseSMSProvider(BaseProvider):
    """A virtual-number provider.

    Implement these seven methods and the whole bot works against the new
    provider. See ``app/providers/sms_activate.py`` for a worked example.
    """

    supports_rental: bool = False

    @abstractmethod
    async def get_services(self) -> list[SmsService]:
        """Full service catalogue. Cached by the service layer."""

    @abstractmethod
    async def get_countries(self, service_code: str) -> list[SmsCountry]:
        """Countries offering ``service_code``, with costs and availability."""

    @abstractmethod
    async def get_price(self, service_code: str, country_id: int) -> int:
        """Authoritative current cost, in minor units. Re-checked before purchase."""

    @abstractmethod
    async def create_activation(self, service_code: str, country_id: int) -> Activation:
        """Buy a number. Never retried automatically -- a retry could double-buy."""

    @abstractmethod
    async def get_activation_status(self, provider_order_id: str) -> ActivationStatus:
        """Poll an activation for its SMS."""

    @abstractmethod
    async def cancel_activation(self, provider_order_id: str) -> bool:
        """Release a number back to the provider."""

    @abstractmethod
    async def finish_activation(self, provider_order_id: str) -> bool:
        """Confirm the code was used, so the provider closes the activation."""

    async def get_rental_countries(self) -> list[SmsCountry]:
        """Countries that offer rentals. Often a subset of activation countries."""
        raise NotImplementedError(f"{self.name} does not support rentals")

    async def get_rental_services(self, country_id: int, hours: int) -> list[RentalOffer]:
        """Rentable services for a country and duration, with real costs."""
        raise NotImplementedError(f"{self.name} does not support rentals")

    async def create_rental(self, service_code: str, country_id: int, hours: int) -> Rental:
        raise NotImplementedError(f"{self.name} does not support rentals")

    async def get_rental_messages(self, provider_order_id: str) -> list[RentalMessage]:
        raise NotImplementedError(f"{self.name} does not support rentals")

    async def cancel_rental(self, provider_order_id: str) -> bool:
        raise NotImplementedError(f"{self.name} does not support rentals")


class BasePaymentProvider(BaseProvider):
    """A deposit gateway."""

    #: Whether the provider pushes updates (webhook) or must be polled.
    supports_polling: bool = True
    #: Set when Telegram itself handles the checkout UI (Stars).
    is_native: bool = False

    @abstractmethod
    async def create_invoice(self, user_id: int, amount: int, description: str) -> Invoice:
        """Create an invoice for ``amount`` minor units.

        Must never be retried blindly: a retried create can leave a second
        unpaid invoice behind.
        """

    @abstractmethod
    async def check_payment(self, invoice_id: str) -> str:
        """Return the current status: ``pending``, ``paid``, ``expired`` or ``failed``."""

    async def cancel_invoice(self, invoice_id: str) -> bool:
        """Best-effort cancellation. Returning False is not an error."""
        return False


class BaseSMMProvider(BaseProvider):
    """An SMM panel."""

    @abstractmethod
    async def get_services(self) -> list[SmmService]:
        """Full service catalogue, normalised into :class:`SmmService`."""

    @abstractmethod
    async def create_order(self, service_id: str, link: str, quantity: int) -> str:
        """Place an order and return the provider's order id."""

    @abstractmethod
    async def get_order_status(self, provider_order_id: str) -> SmmOrderStatus:
        """Poll one order."""
