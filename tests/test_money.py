"""Money conversions. Float error here would be money error in production."""

from decimal import Decimal

import pytest

from app.core.money import (
    apply_percent,
    format_money,
    parse_amount,
    round_up_minor,
    to_major,
    to_minor,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("12.34", 1234), (0.1, 10), (Decimal("0.005"), 1), (100, 10_000), ("0", 0)],
)
def test_to_minor(value, expected):
    assert to_minor(value) == expected


def test_to_minor_survives_float_representation():
    # 0.1 + 0.2 == 0.30000000000000004 in binary floating point.
    assert to_minor(0.1 + 0.2) == 30


def test_round_trip():
    assert to_major(to_minor("99.99")) == Decimal("99.99")


def test_round_up_never_undercharges():
    assert round_up_minor(Decimal("0.001")) == 1
    assert round_up_minor(Decimal("10.001")) == 1001


def test_apply_percent():
    assert apply_percent(1000, Decimal("10")) == 100
    assert apply_percent(1005, Decimal("10")) == 101  # rounds half-up


def test_format_money():
    assert format_money(123_456, "₹") == "₹1,234.56"
    assert format_money(-500, "₹") == "-₹5.00"


@pytest.mark.parametrize("text", ["abc", "", "-5", "0", "1e9999999"])
def test_parse_amount_rejects_junk(text):
    assert parse_amount(text) is None


def test_parse_amount_accepts_formatted_input():
    assert parse_amount(" ₹1,234.50 ") == 123_450


@pytest.mark.parametrize("text", ["nan", "NaN", "-nan", "snan", "inf", "-inf", "Infinity"])
def test_parse_amount_rejects_nan_and_infinity_without_raising(text):
    """Comparing a NaN Decimal with <= raises InvalidOperation; must not crash the handler."""
    assert parse_amount(text) is None


@pytest.mark.parametrize("text", ["0.001", "0.004", "1e-100", "0.0001"])
def test_parse_amount_rejects_values_that_round_to_zero_minor_units(text):
    assert parse_amount(text) is None


def test_parse_amount_never_raises():
    for text in ["nan", "inf", "-inf", "snan", "1e-400", "🙂", "0.001", "--5", "5..5"]:
        parse_amount(text)  # must not raise
