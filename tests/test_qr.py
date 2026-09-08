"""UPI links and QR rendering.

The amount travels inside the code, so these assertions are about money
reaching the right place in the right size.
"""

from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from app.utils.qr import build_upi_link, is_valid_vpa, render_qr


def _params(link: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(link).query).items()}


def test_link_carries_payee_and_amount():
    link = build_upi_link("shop@okaxis", "My Shop", Decimal("500"))
    assert link.startswith("upi://pay?")

    params = _params(link)
    assert params["pa"] == "shop@okaxis"
    assert params["pn"] == "My Shop"
    assert params["am"] == "500.00"
    assert params["cu"] == "INR"


def test_amount_always_has_two_decimals():
    """A UPI app reading '500' and '500.5' should get an unambiguous figure."""
    assert _params(build_upi_link("a@b", "X", Decimal("500")))["am"] == "500.00"
    assert _params(build_upi_link("a@b", "X", Decimal("500.5")))["am"] == "500.50"
    assert _params(build_upi_link("a@b", "X", Decimal("0.01")))["am"] == "0.01"


def test_special_characters_in_the_payee_name_are_encoded():
    link = build_upi_link("shop@okaxis", "Ram & Co / Traders", Decimal("10"))
    assert " " not in link
    assert _params(link)["pn"] == "Ram & Co / Traders"


def test_note_and_reference_are_optional_and_bounded():
    plain = _params(build_upi_link("a@b", "X", Decimal("10")))
    assert "tn" not in plain and "tr" not in plain

    full = _params(build_upi_link("a@b", "X", Decimal("10"), note="x" * 80, reference="y" * 80))
    assert len(full["tn"]) == 50
    assert len(full["tr"]) == 35


@pytest.mark.parametrize("vpa", ["shop@okaxis", "a.b-c_1@ybl", "9876543210@paytm"])
def test_valid_vpas_are_accepted(vpa):
    assert is_valid_vpa(vpa) is True


@pytest.mark.parametrize(
    "vpa", ["", "nohandle", "a@b@c", "@okaxis", "shop@", "shop okaxis@ybl", "shop@.ybl"]
)
def test_invalid_vpas_are_rejected(vpa):
    assert is_valid_vpa(vpa) is False


def test_qr_renders_a_png():
    png = render_qr(build_upi_link("shop@okaxis", "My Shop", Decimal("500")))
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 500


def test_a_longer_payload_still_renders():
    """Version is chosen to fit, so a long note must not overflow the code."""
    link = build_upi_link("averylongname.with.dots@somebank", "A" * 40, Decimal("12345.67"),
                          note="B" * 50, reference="C" * 35)
    assert render_qr(link).startswith(b"\x89PNG")


def _decode(png: bytes) -> str:
    """Read a QR back out of its PNG, the way a phone camera would."""
    import io

    cv2 = pytest.importorskip("cv2", reason="opencv is a dev-only dependency")
    numpy = pytest.importorskip("numpy")
    from PIL import Image

    image = numpy.array(Image.open(io.BytesIO(png)).convert("RGB"))[:, :, ::-1]
    decoded, _points, _straight = cv2.QRCodeDetector().detectAndDecode(image)
    return decoded


def test_the_rendered_code_scans_back_to_the_same_link():
    """A QR nobody can scan is worse than no QR, so decode it and compare."""
    link = build_upi_link("shop@okaxis", "My Shop", Decimal("500"), note="Top-up")

    assert _decode(render_qr(link)) == link


def test_the_scanned_code_carries_the_right_amount():
    """The whole point of generating it: the payer cannot type a different sum."""
    link = build_upi_link("shop@okaxis", "My Shop", Decimal("1234.50"))

    assert _params(_decode(render_qr(link)))["am"] == "1234.50"


def test_a_small_code_still_scans():
    """Telegram compresses images; the code must survive at a modest size."""
    link = build_upi_link("shop@okaxis", "My Shop", Decimal("99"))

    assert _decode(render_qr(link, box_size=4)) == link
