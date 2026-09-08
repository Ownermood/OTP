"""Callback data schemas.

Callback payloads stay short and carry **no** authoritative values -- no price,
no user id, no balance. Anything that decides money is looked up server-side
from the token store or the database. See :mod:`app.utils.tokens`.

Optional string fields are declared ``str | None = None``, never ``str = ""``.
aiogram packs an empty string and unpacks it back as ``None``, so a ``str``
field with an empty default fails validation on the way in and the callback is
dropped without reaching a handler -- a button that silently does nothing.
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
    provider: str | None = None
    payment_id: int = 0


class RentCB(CallbackData, prefix="rnt"):
    """Rental navigation.

    ``country`` picks a country, ``hours`` a duration (``0`` opens the custom
    prompt), and ``quote`` carries a server-side token, never a price.
    """

    action: str
    value: str | None = None
    page: int = 1


class SmmCB(CallbackData, prefix="smm"):
    action: str
    value: str | None = None
    page: int = 1


class TransferCB(CallbackData, prefix="trf"):
    """Confirm a balance transfer.

    Its own prefix rather than a shared confirm token: the buy router owns
    ConfirmCB and would consume a transfer's token before this ever saw it.
    """

    token: str


class ManualCB(CallbackData, prefix="man"):
    """Approve or decline a manual deposit from the review channel.

    Carries only the request id. Whether the tapper may decide it is resolved
    from the configured admin roles, never from this payload.
    """

    action: str
    payment_id: int


class HelpCB(CallbackData, prefix="hlp"):
    topic: str


class SettingsCB(CallbackData, prefix="set"):
    action: str
    value: str | None = None


class AdminCB(CallbackData, prefix="adm"):
    """Admin navigation. Permission is checked from configured roles, never here."""

    action: str
    value: str | None = None
    page: int = 1


class NoopCB(CallbackData, prefix="noop"):
    """Inert button (page counters, headers)."""
