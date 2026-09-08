"""Manual UPI / bank deposits, from submission to approval."""

import pytest

from tests.flow_helpers import REVIEW_CHANNEL


@pytest.fixture
def manual_harness(harness, settings):
    """Manual deposits on, with the driving user as the reviewing admin."""
    settings.manual_payment_enabled = True
    settings.manual_payment_channel_id = REVIEW_CHANNEL
    settings.admin_ids = [harness.user_id]
    settings.admin_roles = {}
    return harness


async def _submit_manual(h, amount="500", utr="402199881122") -> str:
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send(amount)
    await h.tap("I Have Paid")
    await h.send(utr)
    await h.send_photo("screenshot-1")
    return h.posted_to(REVIEW_CHANNEL)[0].callback_for("Approve")


async def test_manual_deposit_reaches_the_review_channel(manual_harness):
    """Amount → UTR → screenshot → posted for review, balance untouched."""
    from app.services.wallet import WalletService

    h = manual_harness
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")

    assert "UPI / QR" in " ".join(h.buttons())
    await h.tap("UPI / QR")
    assert "UPI DEPOSIT" in h.text

    await h.send("500")
    # The QR arrives as a photo, with the amount already inside the code.
    qr = h.session.sent[-1]
    assert qr.method == "SendPhoto"
    assert "UPI DEPOSIT" in qr.text
    assert "shop@okaxis" in qr.text
    assert "₹500.00" in qr.text
    assert "verifies the payment" in qr.text
    assert qr.buttons() == ["✅ I Have Paid", "❌ Cancel"]

    await h.tap("I Have Paid")
    assert "UTR / TRANSACTION ID" in h.text

    await h.send("4021-9988-1122")
    assert "PAYMENT SCREENSHOT" in h.text
    assert "402199881122" in h.text  # normalised

    await h.send_photo("screenshot-1")
    assert "AWAITING APPROVAL" in h.text

    posted = h.posted_to(REVIEW_CHANNEL)
    assert len(posted) == 1
    assert posted[0].method == "SendPhoto"
    assert "DEPOSIT REQUEST" in posted[0].text
    assert "402199881122" in posted[0].text
    assert "₹500.00" in posted[0].text
    assert posted[0].buttons() == ["✅ Approve", "❌ Decline"]

    # Nothing has been credited yet.
    async with h.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(h.user_id) == 0


async def test_approving_from_the_channel_credits_and_notifies(manual_harness):
    from app.services.wallet import WalletService

    h = manual_harness
    approve = await _submit_manual(h)

    await h.press(approve)

    async with h.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(h.user_id) == 50_000

    notice = next(s.text for s in h.session.screens if "PAYMENT APPROVED" in s.text)
    assert "₹500.00" in notice


async def test_a_non_admin_tapping_approve_is_refused(harness, settings):
    """The buttons sit in a channel; the permission is not in the tap."""
    from app.services.wallet import WalletService

    settings.manual_payment_enabled = True
    settings.manual_payment_channel_id = REVIEW_CHANNEL
    settings.admin_ids = [999999]  # somebody else entirely
    settings.admin_roles = {}

    approve = await _submit_manual(harness)
    await harness.press(approve)

    assert "do not have access" in harness.text
    async with harness.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(harness.user_id) == 0


async def test_approving_twice_credits_once(manual_harness):
    from app.services.wallet import WalletService

    h = manual_harness
    approve = await _submit_manual(h)

    await h.press(approve)
    h.forget_last_tap()
    await h.press(approve)

    assert any("already been reviewed" in a for a in h.alerts)
    async with h.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(h.user_id) == 50_000


async def test_declining_asks_for_a_reason_and_credits_nothing(manual_harness):
    from app.services.wallet import WalletService

    h = manual_harness
    await _submit_manual(h)
    decline = h.posted_to(REVIEW_CHANNEL)[0].callback_for("Decline")

    await h.press(decline)
    assert "DECLINE REQUEST" in h.text

    await h.send("amount does not match the screenshot")
    assert any("declined" in s.text.lower() for s in h.session.screens)

    notice = next(s.text for s in h.session.screens if "PAYMENT DECLINED" in s.text)
    assert "amount does not match" in notice

    async with h.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(h.user_id) == 0


async def test_a_reused_reference_is_rejected_at_submission(manual_harness):
    h = manual_harness
    await _submit_manual(h)

    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")
    await h.tap("I Have Paid")
    await h.send("402199881122")  # the same payment, claimed again
    await h.send_photo("screenshot-1")

    assert "already being processed" in h.text
    assert len(h.posted_to(REVIEW_CHANNEL)) == 0


async def test_a_bad_reference_is_rejected_before_the_screenshot(manual_harness):
    h = manual_harness
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")
    await h.tap("I Have Paid")
    await h.send("123")  # too short to be a real reference

    assert "does not look right" in h.text.lower()


async def test_text_instead_of_a_screenshot_is_named_not_ignored(manual_harness):
    h = manual_harness
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")
    await h.tap("I Have Paid")
    await h.send("402199881122")

    await h.send("here is my payment, trust me")
    assert "send the screenshot as a photo" in h.text.lower()


# -- confirmations before irreversible actions ------------------------------
