"""Pricing is the only place a markup is applied."""

from decimal import Decimal

from app.services.pricing import PricingService


def test_percent_and_fixed_fee(settings):
    settings.service_fee_percent = Decimal("5")
    settings.service_fee_fixed = Decimal("2")
    breakdown = PricingService(settings).quote(1000)

    assert breakdown.provider_cost == 1000
    assert breakdown.percent_fee == 50
    assert breakdown.fixed_fee == 200
    assert breakdown.total == 1250
    assert breakdown.markup == 250


def test_minimum_price_floor(settings):
    settings.min_price = Decimal("20")
    assert PricingService(settings).quote(100).total == 2000


def test_maximum_price_ceiling(settings):
    settings.max_price = Decimal("5")
    assert PricingService(settings).quote(100_000).total == 500


def test_smm_prorates_per_thousand(settings):
    settings.smm_markup_percent = Decimal("0")
    # 100.00 per 1000 units, ordering 500 units => 50.00
    assert PricingService(settings).quote_smm(10_000, 500).total == 5_000


def test_smm_small_order_rounds_up_not_down(settings):
    settings.smm_markup_percent = Decimal("0")
    # A single unit of a 10.00/1000 service costs a fraction of a paisa.
    # Rounding down would sell it for nothing.
    assert PricingService(settings).quote_smm(1000, 1).total == 1
