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
    await h.tap("I Have Paid")
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
    await h.tap("I Have Paid")
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


# -- using your own QR image instead of a generated one ---------------------


@pytest.fixture
def static_qr(tmp_path, upi_harness, settings):
    """An operator who supplies their own QR rather than a UPI id."""
    from decimal import Decimal

    from app.utils.qr import build_upi_link, render_qr

    image = tmp_path / "my-qr.png"
    image.write_bytes(render_qr(build_upi_link("myshop@okaxis", "My Shop", Decimal("1"))))

    settings.upi_id = ""
    settings.upi_qr_image = str(image)
    return upi_harness


async def test_a_static_qr_is_sent_when_no_upi_id_is_set(static_qr):
    h = static_qr
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")

    qr = h.session.sent[-1]
    assert qr.method == "SendPhoto"
    # A static code carries no amount, so the caption has to state it plainly.
    assert "Pay <b>exactly ₹500.00</b>" in qr.text


async def test_a_static_qr_deposit_still_completes(static_qr, session_factory):
    from app.services.wallet import WalletService

    h = static_qr
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")
    await h.tap("I Have Paid")
    await h.send("402199881122")
    await h.send_photo("proof")

    assert "AWAITING APPROVAL" in h.text
    await h.press(h.posted_to(REVIEW_CHANNEL)[0].callback_for("Approve"))

    async with session_factory() as session:
        assert await WalletService(session).get_balance(h.user_id) == 50_000


async def test_a_missing_qr_file_does_not_strand_the_user(upi_harness, settings):
    """A path that points at nothing must still let the deposit continue."""
    settings.upi_id = ""
    settings.upi_qr_image = "/nonexistent/qr.png"

    h = upi_harness
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")

    # Falls back to the same details as text rather than sending nothing.
    assert "UPI DEPOSIT" in h.text
    assert "I Have Paid" in " ".join(h.buttons())


async def test_a_relative_qr_path_resolves_against_the_project(monkeypatch):
    from app.core.config import ROOT_DIR, Settings

    monkeypatch.setenv("MANUAL_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("MANUAL_PAYMENT_CHANNEL_ID", "-1001234567890")
    monkeypatch.setenv("UPI_ID", "")
    monkeypatch.setenv("UPI_QR_IMAGE", "assets/qr.png")

    assert Settings().qr_image_path == ROOT_DIR / "assets" / "qr.png"


# -- the "I Have Paid" gate -------------------------------------------------


async def test_the_reference_is_not_asked_for_until_the_user_says_they_paid(upi_harness):
    """Without the gate, any stray message after the QR reads as a reference."""
    h = upi_harness
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")

    # A message sent while the QR is up must not be taken as a UTR, and the
    # bot must say so rather than going quiet.
    await h.send("402199881122")
    assert "I Have Paid" in h.text
    assert len(h.posted_to(REVIEW_CHANNEL)) == 0

    await h.tap("I Have Paid")
    assert "UTR / TRANSACTION ID" in h.text


async def test_cancelling_at_the_qr_screen_leaves_no_request(upi_harness):
    h = upi_harness
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")

    await h.tap("Cancel")
    assert "WALLET" in h.text
    assert len(h.posted_to(REVIEW_CHANNEL)) == 0


async def test_i_have_paid_without_an_amount_does_not_proceed(upi_harness):
    """A stale button from an abandoned attempt must not open the UTR prompt."""
    from app.bot.callbacks import PaymentCB

    h = upi_harness
    await h.send("/start")
    await h.press(PaymentCB(action="paid", provider="manual").pack())

    assert any("expired" in alert.lower() for alert in h.alerts)


# -- the amount floor -------------------------------------------------------


async def test_the_minimum_deposit_is_enforced(upi_harness):
    h = upi_harness
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")

    assert "₹100.00" in h.text  # stated up front

    await h.send("50")
    assert "does not look right" in h.text.lower()


async def test_exactly_the_minimum_is_accepted(upi_harness):
    h = upi_harness
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("100")

    qr = h.session.sent[-1]
    assert qr.method == "SendPhoto"
    assert "₹100.00" in qr.text


# -- which QR is shown ------------------------------------------------------


async def test_your_own_qr_wins_over_a_generated_one(tmp_path, upi_harness, settings):
    """Setting both means you branded a code and expect everyone to see it."""
    from decimal import Decimal

    from app.utils.qr import build_upi_link, render_qr

    image = tmp_path / "branded.png"
    image.write_bytes(render_qr(build_upi_link("myshop@okaxis", "My Shop", Decimal("1"))))
    settings.upi_id = "shop@okaxis"      # still shown as text in the caption
    settings.upi_qr_image = str(image)

    h = upi_harness
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")

    qr = h.session.sent[-1]
    # The file was sent, not a freshly rendered buffer.
    assert type(qr.payload["photo"]).__name__ == "FSInputFile"
    # The UPI id is still on screen, so it can be copied instead of scanned.
    assert "shop@okaxis" in qr.text
