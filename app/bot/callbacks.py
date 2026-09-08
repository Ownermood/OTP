"""Callback data schemas.

Callback payloads stay short and carry **no** authoritative values -- no price,
no user id, no balance. Anything that decides money is looked up server-side
from the token store or the database. See :mod:`app.utils.tokens`.
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class Nav(CallbackData, prefix="nav"):
    """Top-level navigation between screens."""

    to: str
    page: int = 1


class ServiceCB(CallbackData, prefix="svc"):
    """Pick an SMS service. ``code`` is a provider service code, not a price."""

    code: str
    page: int = 1


class CountryCB(CallbackData, prefix="cty"):
    """Pick a country for a service. The quote lives behind ``token``."""

    token: str


class ConfirmCB(CallbackData, prefix="cfm"):
    """Confirm a purchase. ``token`` is single-use, which stops double taps."""

    token: str


class OrderCB(CallbackData, prefix="ord"):
    """Act on one of the user's own orders. Ownership is re-checked server-side."""

    action: str
    order_id: int


class OrdersListCB(CallbackData, prefix="orl"):
    kind: str
    page: int = 1


class FavoriteCB(CallbackData, prefix="fav"):
    action: str
    favorite_id: int


class WalletCB(CallbackData, prefix="wal"):
    action: str
    page: int = 1


class PaymentCB(CallbackData, prefix="pay"):
    action: str
    provider: str = ""
    payment_id: int = 0


class RentCB(CallbackData, prefix="rnt"):
    """Rental navigation.

    ``country`` picks a country, ``hours`` a duration (``0`` opens the custom
    prompt), and ``quote`` carries a server-side token, never a price.
    """

    action: str
    value: str = ""
    page: int = 1


class SmmCB(CallbackData, prefix="smm"):
    action: str
    value: str = ""
    page: int = 1


class HelpCB(CallbackData, prefix="hlp"):
    topic: str


class SettingsCB(CallbackData, prefix="set"):
    action: str
    value: str = ""


class AdminCB(CallbackData, prefix="adm"):
    """Admin navigation. Permission is checked from configured roles, never here."""

    action: str
    value: str = ""
    page: int = 1


class NoopCB(CallbackData, prefix="noop"):
    """Inert button (page counters, headers)."""
