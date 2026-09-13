"""Manual UPI / bank deposits, from submission to approval."""

import pytest
from sqlalchemy import select

from app.core.constants import PaymentStatus
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
    assert [b.lower() for b in qr.buttons()] == ["📋 copy upi id", "✅ i have paid", "❌ cancel"]

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
    """Approve moves real money, so it asks for confirmation first."""
    from app.services.wallet import WalletService

    h = manual_harness
    approve = await _submit_manual(h)

    await h.press(approve)
    assert h.buttons() == ["✅ Yes, Approve", "❌ Cancel"]
    async with h.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(h.user_id) == 0  # not yet

    confirm = h.screen.callback_for("Yes, Approve")
    await h.press(confirm)

    async with h.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(h.user_id) == 50_000

    notice = next(s.text for s in h.session.screens if "PAYMENT APPROVED" in s.text)
    assert "₹500.00" in notice


async def test_cancelling_the_approve_confirmation_credits_nothing(manual_harness):
    from app.services.wallet import WalletService

    h = manual_harness
    approve = await _submit_manual(h)

    await h.press(approve)
    cancel = h.screen.callback_for("Cancel")
    await h.press(cancel)

    assert h.buttons() == ["✅ Approve", "❌ Decline"]
    async with h.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(h.user_id) == 0

    # And it can still be approved normally afterwards.
    confirm_again = h.screen.callback_for("Approve")
    await h.press(confirm_again)
    yes = h.screen.callback_for("Yes, Approve")
    await h.press(yes)
    async with h.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(h.user_id) == 50_000


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
    confirm = h.screen.callback_for("Yes, Approve")
    await h.press(confirm)
    h.forget_last_tap()
    await h.press(confirm)

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


# -- reviewing from the panel when the channel is not an option -------------


async def test_pending_deposits_are_visible_in_the_panel(manual_harness):
    """Regression: a failed channel post left requests invisible in the DB."""
    h = manual_harness
    await _submit_manual(h)

    await h.send("/admin")
    await h.tap("Payments")
    await h.tap("Pending deposits")

    assert "PENDING DEPOSITS" in h.text
    assert "1 request" in h.text
    assert any("402199881122" in b for b in h.buttons())


async def test_a_missed_notification_can_be_resent(manual_harness, monkeypatch, session_factory):
    """A payment whose review post never landed must be recoverable -- without
    creating a new payment, touching the wallet, or changing its UTR/status."""
    from aiogram.exceptions import TelegramBadRequest

    from app.database.models import Payment
    from tests.harness import MockedSession

    h = manual_harness
    original = MockedSession.make_request
    blocked = True

    async def sometimes_failing(self, bot, method, timeout=None):
        name = type(method).__name__
        if blocked and name in ("SendPhoto", "SendMessage") and getattr(
            method, "chat_id", None
        ) == REVIEW_CHANNEL:
            raise TelegramBadRequest(method=method, message="Bad Request: chat not found")
        return await original(self, bot, method, timeout)

    monkeypatch.setattr(MockedSession, "make_request", sometimes_failing)

    # The channel is "down" for this whole submission -- can't use
    # _submit_manual, which assumes the review post lands.
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")
    await h.tap("I Have Paid")
    await h.send("402199881122")
    await h.send_photo("screenshot-1")

    async with session_factory() as session:
        payment = await session.get(Payment, 1)
        assert payment.review_message_id is None  # confirmed missing

    await h.send("/admin")
    await h.tap("Payments")
    await h.tap("Pending deposits")
    assert "⚠️" in h.text or any("⚠️" in b for b in h.buttons())

    blocked = False  # the channel is back
    await h.tap("402199881122")
    assert "Missing" in h.text or "Resend" in " ".join(h.buttons())

    await h.tap("Resend")

    posted = h.posted_to(REVIEW_CHANNEL)
    assert len(posted) == 1  # this resend, not the original failed attempt

    async with session_factory() as session:
        result = await session.execute(select(Payment).where(Payment.provider == "manual"))
        payments = result.scalars().all()
        assert len(payments) == 1  # no duplicate payment created

        payment = await session.get(Payment, 1)
        assert payment.review_message_id is not None
        assert payment.status == PaymentStatus.PENDING
        assert payment.invoice_id == "402199881122"

    async with session_factory() as session:
        from app.services.wallet import WalletService

        assert await WalletService(session).get_balance(h.user_id) == 0


async def test_a_stale_photo_falls_back_to_a_text_review_message(
    manual_harness, monkeypatch, session_factory
):
    """The review post itself must survive a rejected photo (e.g. a stale
    file_id from before a bot token change) -- not just the admin panel."""
    from aiogram.exceptions import TelegramBadRequest

    from app.database.models import Payment
    from tests.harness import MockedSession

    h = manual_harness
    original = MockedSession.make_request

    async def failing_make_request(self, bot, method, timeout=None):
        # Only the photo aimed at the review channel is stale -- the QR sent
        # to the user themselves must still work normally.
        if type(method).__name__ == "SendPhoto" and getattr(method, "chat_id", None) == REVIEW_CHANNEL:
            raise TelegramBadRequest(
                method=method, message="Bad Request: wrong file identifier/HTTP URL specified"
            )
        return await original(self, bot, method, timeout)

    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")
    await h.tap("I Have Paid")
    await h.send("402199881122")

    monkeypatch.setattr(MockedSession, "make_request", failing_make_request)
    await h.send_photo("screenshot-1")

    posted = h.posted_to(REVIEW_CHANNEL)
    assert len(posted) == 1
    assert posted[0].method == "SendMessage"
    assert "DEPOSIT REQUEST" in posted[0].text
    assert posted[0].buttons() == ["✅ Approve", "❌ Decline"]

    async with session_factory() as session:
        payment = await session.get(Payment, 1)
        assert payment.review_message_id is not None


async def test_a_total_channel_outage_notifies_admins_and_keeps_the_payment_pending(
    manual_harness, monkeypatch, session_factory
):
    """When photo AND text both fail, the request must not be lost or stuck
    invisible -- admins get a direct DM, and the payment stays recoverable."""
    from aiogram.exceptions import TelegramBadRequest

    from app.database.models import Payment
    from tests.harness import MockedSession

    h = manual_harness
    original = MockedSession.make_request

    async def total_outage(self, bot, method, timeout=None):
        name = type(method).__name__
        if name in ("SendPhoto", "SendMessage") and getattr(method, "chat_id", None) == REVIEW_CHANNEL:
            raise TelegramBadRequest(method=method, message="Bad Request: chat not found")
        return await original(self, bot, method, timeout)

    monkeypatch.setattr(MockedSession, "make_request", total_outage)

    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")
    await h.tap("I Have Paid")
    await h.send("402199881122")
    await h.send_photo("screenshot-1")

    assert len(h.posted_to(REVIEW_CHANNEL)) == 0  # nothing reached the channel
    # The admin (the reviewer here) gets a direct DM about the failure.
    assert any("could not be posted" in s.text for s in h.session.screens)

    async with session_factory() as session:
        payment = await session.get(Payment, 1)
        assert payment.review_message_id is None
        assert payment.status == PaymentStatus.PENDING  # never lost


async def test_approving_a_nonexistent_payment_is_refused_cleanly(manual_harness):
    from app.bot.callbacks import ManualCB

    h = manual_harness
    await h.send("/start")
    await h.press(ManualCB(action="approve_confirm", payment_id=999).pack())

    assert any("not found" in a.lower() for a in h.alerts)


async def test_resending_a_nonexistent_payment_is_refused_cleanly(manual_harness):
    from app.bot.callbacks import ManualCB

    h = manual_harness
    await h.send("/start")
    await h.press(ManualCB(action="resend", payment_id=999).pack())

    assert any("not found" in a.lower() for a in h.alerts)


async def test_a_stale_proof_photo_does_not_hide_the_review_screen(manual_harness, monkeypatch):
    """Regression: a rejected photo (e.g. a stale file_id from before a bot
    token change) must not leave the admin staring at a dead, empty tap --
    Approve/Decline must still render as a text-only fallback."""
    from aiogram.exceptions import TelegramBadRequest

    from tests.harness import MockedSession

    h = manual_harness
    await _submit_manual(h)

    original = MockedSession.make_request

    async def failing_make_request(self, bot, method, timeout=None):
        if type(method).__name__ == "SendPhoto":
            raise TelegramBadRequest(
                method=method, message="Bad Request: wrong file identifier/HTTP URL specified"
            )
        return await original(self, bot, method, timeout)

    monkeypatch.setattr(MockedSession, "make_request", failing_make_request)

    await h.send("/admin")
    await h.tap("Payments")
    await h.tap("Pending deposits")
    await h.tap("402199881122")

    assert "DEPOSIT REQUEST" in h.text
    assert h.screen.buttons() == ["✅ Approve", "❌ Decline"]


async def test_an_empty_queue_says_so(manual_harness):
    h = manual_harness
    await h.send("/start")
    await h.send("/admin")
    await h.tap("Payments")
    await h.tap("Pending deposits")

    assert "Nothing is waiting" in h.text


async def test_a_request_can_be_approved_from_the_panel(manual_harness, session_factory):
    """The channel post is convenience; the panel is the fallback that works."""
    from app.services.wallet import WalletService

    h = manual_harness
    await _submit_manual(h)

    await h.send("/admin")
    await h.tap("Payments")
    await h.tap("Pending deposits")
    await h.tap("402199881122")

    assert "DEPOSIT REQUEST" in h.text
    assert h.screen.buttons() == ["✅ Approve", "❌ Decline"]

    await h.tap("Approve")
    assert h.buttons() == ["✅ Yes, Approve", "❌ Cancel"]
    await h.tap("Yes, Approve")
    async with session_factory() as session:
        assert await WalletService(session).get_balance(h.user_id) == 50_000


async def test_an_approved_request_leaves_the_queue(manual_harness):
    h = manual_harness
    await _submit_manual(h)

    approve = h.posted_to(REVIEW_CHANNEL)[0].callback_for("Approve")
    await h.press(approve)
    confirm = h.screen.callback_for("Yes, Approve")
    await h.press(confirm)

    await h.send("/admin")
    await h.tap("Payments")
    await h.tap("Pending deposits")

    assert "Nothing is waiting" in h.text


async def test_a_non_reviewer_cannot_open_a_pending_request(manual_harness, settings):
    from app.bot.callbacks import ManualCB

    h = manual_harness
    await _submit_manual(h)

    settings.admin_ids = [999999]  # somebody else entirely
    settings.admin_roles = {}
    await h.press(ManualCB(action="open", payment_id=1).pack())

    assert "do not have access" in h.text


async def test_an_ordinary_user_cannot_resend_a_review(manual_harness, settings):
    """Resend moves no money, but it is still admin-only -- server-checked."""
    from app.bot.callbacks import ManualCB

    h = manual_harness
    await _submit_manual(h)

    settings.admin_ids = [999999]  # somebody else entirely
    settings.admin_roles = {}
    await h.press(ManualCB(action="resend", payment_id=1).pack())

    assert "do not have access" in h.text
