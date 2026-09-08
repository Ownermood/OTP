"""Money handling.

Money is stored and passed around as ``int`` **minor units** (paise/cents).
Floats are never used for balances, prices or transaction amounts -- the only
place a float is tolerated is the raw price a provider hands us over HTTP, and
that is converted to minor units immediately at the adapter boundary.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation

MINOR_UNITS = 100
"""Number of minor units in one major unit (100 paise = 1 rupee)."""


def to_minor(value: Decimal | int | float | str) -> int:
    """Convert a major-unit amount (``12.34``) to minor units (``1234``)."""
    return int(_as_decimal(value).scaleb(2).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_major(minor: int) -> Decimal:
    """Convert minor units (``1234``) back to a major-unit ``Decimal`` (``12.34``)."""
    return (Decimal(minor) / MINOR_UNITS).quantize(Decimal("0.01"))


def round_up_minor(value: Decimal | int | float | str) -> int:
    """Convert to minor units, always rounding *up*.

    Used for prices charged to the user so rounding never eats into margin.
    """
    return int(_as_decimal(value).scaleb(2).quantize(Decimal("1"), rounding=ROUND_CEILING))


def apply_percent(minor: int, percent: Decimal) -> int:
    """Return ``percent`` percent of ``minor``, rounded half-up."""
    return int((Decimal(minor) * percent / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_money(minor: int, symbol: str = "₹") -> str:
    """Render minor units for display: ``1234`` -> ``₹12.34``."""
    amount = to_major(minor)
    sign = "-" if amount < 0 else ""
    return f"{sign}{symbol}{abs(amount):,.2f}"


def parse_amount(text: str) -> int | None:
    """Parse user-typed money into minor units, or ``None`` when invalid."""
    cleaned = text.strip().replace(",", "").replace("₹", "").replace("$", "")
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if value <= 0 or value > Decimal("10000000"):
        return None
    return to_minor(value)


def _as_decimal(value: Decimal | int | float | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        # str() first so 0.1 does not become 0.1000000000000000055511151231257827
        return Decimal(str(value))
    return Decimal(value)
