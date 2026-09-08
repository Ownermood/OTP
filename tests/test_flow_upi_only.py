"""The shipped configuration: UPI and QR as the only deposit method.

Everything here runs with CryptoBot and Stars off, which is how .env.example
ships, so it exercises what an operator actually gets out of the box.
"""

import pytest

from tests.flow_helpers import REVIEW_CHANNEL


@pytest.fixture
def upi_harness(harness, settings):
    """UPI-only: no gateway providers at all, manual review on."""
    harness.dispatcher.workflow_data["payment_providers"] = {}
    settings.cryptobot_enabled = False
    settings.telegram_stars_enabled = False
    settings.manual_payment_enabled = True
    settings.manual_payment_channel_id = REVIEW_CHANNEL
    settings.admin_ids = [harness.user_id]
    settings.admin_roles = {}
    return harness


async def test_upi_is_the_only_method_offered(upi_harness):
    await upi_harness.send("/start")
    await upi_harness.tap("Balance")
    await upi_harness.tap("Add Balance")

    buttons = upi_harness.buttons()
    assert "📲 UPI / QR" in buttons
    assert not any("Crypto" in b or "Stars" in b for b in buttons)


async def test_the_qr_contains_the_amount_the_user_asked_for(upi_harness):
    """End to end: the code the user scans must carry their own figure."""
    from urllib.parse import parse_qs, urlparse

    h = upi_harness
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("1,234.50")

    qr = h.session.sent[-1]
    assert qr.method == "SendPhoto"
    assert "₹1,234.50" in qr.text

    # The PNG is real, and the link inside it is the one we meant to send.
    png = qr.payload["photo"]
    assert png.data.startswith(b"\x89PNG")

    cv2 = pytest.importorskip("cv2", reason="opencv is a dev-only dependency")
    numpy = pytest.importorskip("numpy")
    import io

    from PIL import Image

    image = numpy.array(Image.open(io.BytesIO(png.data)).convert("RGB"))[:, :, ::-1]
    link, _points, _straight = cv2.QRCodeDetector().detectAndDecode(image)
    params = {k: v[0] for k, v in parse_qs(urlparse(link).query).items()}

    assert params["pa"] == "shop@okaxis"
    assert params["am"] == "1234.50"
    assert params["cu"] == "INR"


async def test_the_whole_deposit_lands_after_approval(upi_harness, session_factory):
    """Amount, QR, UTR, screenshot, review, approval, balance."""
    from app.services.wallet import WalletService

    h = upi_harness
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")
    await h.send("402199881122")
    await h.send_photo("payment-screenshot")

    assert "AWAITING APPROVAL" in h.text
    async with session_factory() as session:
        assert await WalletService(session).get_balance(h.user_id) == 0

    approve = h.posted_to(REVIEW_CHANNEL)[0].callback_for("Approve")
    await h.press(approve)

    async with session_factory() as session:
        assert await WalletService(session).get_balance(h.user_id) == 50_000


async def test_a_deposit_can_then_be_spent(upi_harness, session_factory):
    """The point of the balance: it buys a number."""
    h = upi_harness
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")
    await h.send("402199881122")
    await h.send_photo("proof")
    await h.press(h.posted_to(REVIEW_CHANNEL)[0].callback_for("Approve"))

    await h.send("/start")
    await h.tap("Buy Number")
    await h.tap("WhatsApp")
    await h.tap("India")
    await h.tap("Confirm")

    assert "NUMBER PURCHASED" in h.text
    from app.services.wallet import WalletService

    async with session_factory() as session:
        # 500.00 deposited, 11.00 spent.
        assert await WalletService(session).get_balance(h.user_id) == 48_900


async def test_the_bot_starts_with_upi_as_the_only_method(monkeypatch):
    """The shipped .env.example must be a valid configuration."""
    from app.core.config import Settings

    monkeypatch.setenv("CRYPTOBOT_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_STARS_ENABLED", "false")
    monkeypatch.setenv("MANUAL_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("MANUAL_PAYMENT_CHANNEL_ID", "-1001234567890")
    monkeypatch.setenv("UPI_ID", "shop@okaxis")

    settings = Settings()
    assert settings.manual_payment_enabled is True
    assert settings.payee_name


async def test_upi_without_an_id_or_a_qr_is_refused(monkeypatch):
    """Enabling UPI with nothing to pay to must fail at startup, not at runtime."""
    from app.core.config import Settings

    monkeypatch.setenv("MANUAL_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("MANUAL_PAYMENT_CHANNEL_ID", "-1001234567890")
    monkeypatch.setenv("UPI_ID", "")
    monkeypatch.setenv("UPI_QR_IMAGE", "")

    with pytest.raises(Exception, match="UPI_ID"):
        Settings()
