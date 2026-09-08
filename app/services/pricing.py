"""Pricing.

The single place a user-facing price is computed. Handlers never add a fee,
never apply a markup and never read a price out of callback data -- they ask
this service, and they ask it again immediately before charging.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.config import Settings
from app.core.money import apply_percent, round_up_minor, to_minor


@dataclass(frozen=True, slots=True)
class PriceBreakdown:
    """What the user pays, and where each part came from. All minor units."""

    provider_cost: int
    percent_fee: int
    fixed_fee: int
    total: int


class PricingService:
    """Turns a provider cost into a final price using the configured markup."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def quote(self, provider_cost: int, percent_override: Decimal | None = None) -> PriceBreakdown:
        """Compute the price for an SMS activation."""
        percent = self._settings.service_fee_percent if percent_override is None else percent_override
        percent_fee = apply_percent(provider_cost, percent)
        fixed_fee = to_minor(self._settings.service_fee_fixed)
        total = self._clamp(provider_cost + percent_fee + fixed_fee)
        return PriceBreakdown(provider_cost, percent_fee, fixed_fee, total)

    def quote_smm(self, rate_per_1000: int, quantity: int) -> PriceBreakdown:
        """Compute the price of an SMM order of ``quantity`` units.

        The provider quotes per 1000, so the cost is prorated and rounded up --
        never down, which would sell below cost on small orders.
        """
        provider_cost = round_up_minor(Decimal(rate_per_1000 * quantity) / 1000 / 100)
        percent_fee = apply_percent(provider_cost, self._settings.smm_markup_percent)
        total = self._clamp(provider_cost + percent_fee)
        return PriceBreakdown(provider_cost, percent_fee, 0, total)

    def _clamp(self, total: int) -> int:
        """Apply the configured floor and ceiling. A zero bound means 'unset'."""
        minimum = to_minor(self._settings.min_price)
        maximum = to_minor(self._settings.max_price)
        if minimum and total < minimum:
            total = minimum
        if maximum and total > maximum:
            total = maximum
        return total
