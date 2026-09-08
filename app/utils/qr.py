"""UPI payment links and QR codes.

The QR carries the amount, so the user's payment app opens with it already
filled in. That removes the single most common reason a deposit gets declined:
the user typing a different amount from the one they asked the bot for.
"""

from __future__ import annotations

import io
from decimal import Decimal
from urllib.parse import quote

import qrcode

#: Characters a UPI VPA may contain, per the NPCI addressing spec.
_VPA_ALLOWED = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_@"
)


def is_valid_vpa(vpa: str) -> bool:
    """A loose check that catches typos without rejecting valid handles."""
    if vpa.count("@") != 1:
        return False
    name, _, handle = vpa.partition("@")
    if not name or not handle or "." in handle[:1]:
        return False
    return set(vpa) <= _VPA_ALLOWED


def build_upi_link(
    vpa: str, payee_name: str, amount: Decimal, note: str = "", reference: str = ""
) -> str:
    """Build a ``upi://pay`` deep link every Indian payment app understands."""
    params = [
        f"pa={quote(vpa)}",
        f"pn={quote(payee_name or vpa)}",
        f"am={amount:.2f}",
        "cu=INR",
    ]
    if note:
        params.append(f"tn={quote(note[:50])}")
    if reference:
        params.append(f"tr={quote(reference[:35])}")
    return "upi://pay?" + "&".join(params)


def render_qr(payload: str, box_size: int = 10, border: int = 4) -> bytes:
    """Render ``payload`` as a PNG.

    Error correction is set high so the code still scans from a screenshot of a
    screenshot, which is how these tend to travel.
    """
    code = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=border,
    )
    code.add_data(payload)
    code.make(fit=True)

    buffer = io.BytesIO()
    code.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
    return buffer.getvalue()
