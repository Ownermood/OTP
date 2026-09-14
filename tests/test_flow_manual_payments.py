"""Manual UPI / bank deposits, from submission to approval."""

from datetime import datetime

import pytest
from sqlalchemy import select

from app.bot.callbacks import ManualCB
from app.core.constants import AdminRole, PaymentStatus
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
    assert [b.lower() for b in qr.buttons()] == ["📋 copy upi id", "i have paid", "cancel"]

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
    assert posted[0].buttons() == ["Approve", "Decline"]

    # Nothing has been credited yet.
    async with h.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(h.user_id) == 0


async def test_approving_from_the_channel_credits_and_notifies(manual_harness):
    """Approve moves real money, so it asks for confirmation first."""
    from app.services.wallet import WalletService

    h = manual_harness
    approve = await _submit_manual(h)

    await h.press(approve)
    assert h.buttons() == ["Yes, Approve", "Cancel"]
    async with h.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(h.user_id) == 0  # not yet

    confirm = h.screen.callback_for("Yes, Approve")
    await h.press(confirm)

    async with h.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(h.user_id) == 50_000

    notice = next(s.text for s in h.session.screens if "PAYMENT APPROVED" in s.text)
    assert "₹500.00" in notice


async def test_approving_acknowledges_the_callback_so_the_button_stops_spinning(manual_harness):
    """Regression: the success path used to skip answering the callback query,
    so Telegram left the admin's "Yes, Approve" tap spinning indefinitely even
    though the credit had already gone through."""
    h = manual_harness
    approve = await _submit_manual(h)
    await h.press(approve)

    confirm = h.screen.callback_for("Yes, Approve")
    await h.press(confirm)

    assert any(s.method == "AnswerCallbackQuery" for s in h.session.sent)


async def test_a_blocked_user_notification_does_not_break_the_approval(manual_harness, monkeypatch):
    """The credit and the reviewer's own verdict must not depend on the
    depositor's own notification succeeding -- a blocked bot / deleted
    account on their side is routine, not a reason to leave the reviewer's
    tap looking like it failed. See NotificationService._send, which already
    swallows exactly this and returns False rather than raising."""
    from aiogram.exceptions import TelegramForbiddenError

    from app.services.wallet import WalletService
    from tests.harness import MockedSession

    h = manual_harness
    approve = await _submit_manual(h)

    original = MockedSession.make_request

    async def user_has_blocked_the_bot(self, bot, method, timeout=None):
        if type(method).__name__ == "SendMessage" and "PAYMENT APPROVED" in getattr(
            method, "text", ""
        ):
            raise TelegramForbiddenError(
                method=method, message="Forbidden: bot was blocked by the user"
            )
        return await original(self, bot, method, timeout)

    monkeypatch.setattr(MockedSession, "make_request", user_has_blocked_the_bot)

    await h.press(approve)
    confirm = h.screen.callback_for("Yes, Approve")
    await h.press(confirm)  # must not raise despite the notification failing

    # The reviewer's own result screen still shows a completed approval.
    verdict = next(
        s for s in h.session.screens if "APPROVED" in s.text and "request #" in s.text.lower()
    )
    assert str(h.user_id) in verdict.text

    async with h.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(h.user_id) == 50_000


async def test_cancelling_the_approve_confirmation_credits_nothing(manual_harness):
    from app.services.wallet import WalletService

    h = manual_harness
    approve = await _submit_manual(h)

    await h.press(approve)
    cancel = h.screen.callback_for("Cancel")
    await h.press(cancel)

    assert h.buttons() == ["Approve", "Decline"]
    async with h.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(h.user_id) == 0

    # And it can still be approved normally afterwards.
    confirm_again = h.screen.callback_for("Approve")
    await h.press(confirm_again)
    yes = h.screen.callback_for("Yes, Approve")
    await h.press(yes)
    async with h.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(h.user_id) == 50_000


async def _press_in_channel(h, chat_id: int, message_id: int, callback_data: str):
    """Simulate a tap on a specific message in a specific chat.

    ``h.press()`` always fakes the tap as coming from the driving user's own
    private chat, which cannot exercise "tapped on the channel post itself"
    scenarios -- this builds the callback query with the real chat/message it
    claims to be replying about, the way Telegram actually would.
    """
    from aiogram.types import CallbackQuery, Chat, Message, Update

    h._update_id += 1
    message = Message(
        message_id=message_id,
        date=datetime.now(),
        chat=Chat(id=chat_id, type="channel"),
        text="placeholder",
    )
    query = CallbackQuery(
        id=f"cb{h._update_id}",
        from_user=h._user(),
        chat_instance="test",
        data=callback_data,
        message=message,
    )
    h.session.clear()
    await h.dispatcher.feed_update(h.bot, Update(update_id=h._update_id, callback_query=query))
    return h.session.screens[-1] if h.session.screens else None


async def test_the_verdict_is_recorded_even_if_stripping_the_buttons_fails(
    manual_harness, monkeypatch, session_factory
):
    """The two Telegram calls per target are independent: the decision is
    already committed to the database by this point, so a failure removing
    the buttons must not also swallow the verdict reply -- tapped directly on
    the channel post, so there is exactly one target and one verdict."""
    from aiogram.exceptions import TelegramBadRequest

    from app.database.models import Payment
    from tests.harness import MockedSession

    h = manual_harness
    await _submit_manual(h)
    async with session_factory() as session:
        payment = await session.get(Payment, 1)
        review_message_id = payment.review_message_id

    original = MockedSession.make_request

    async def markup_strip_fails(self, bot, method, timeout=None):
        if type(method).__name__ == "EditMessageReplyMarkup":
            raise TelegramBadRequest(
                method=method, message="Bad Request: message can't be edited"
            )
        return await original(self, bot, method, timeout)

    monkeypatch.setattr(MockedSession, "make_request", markup_strip_fails)
    await _press_in_channel(
        h,
        REVIEW_CHANNEL,
        review_message_id,
        ManualCB(action="approve", payment_id=1).pack(),
    )

    # The verdict reply ("APPROVED — request #1 by ...") is distinct from the
    # separate "PAYMENT APPROVED" notice sent to the user. Tapped directly on
    # the channel post: the channel *is* the only target, so exactly one.
    verdict_posts = [s for s in h.session.screens if " by " in s.text]
    assert len(verdict_posts) == 1


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


async def test_the_second_approve_tap_reports_outcome_reviewer_and_time(manual_harness):
    """The 'already processed' alert is a real state, not a bare shrug --
    it names what happened, who decided it and when, straight from the
    persisted row (payment.status/reviewed_by/reviewed_at)."""
    h = manual_harness
    approve = await _submit_manual(h)

    await h.press(approve)
    confirm = h.screen.callback_for("Yes, Approve")
    await h.press(confirm)
    h.forget_last_tap()
    await h.press(confirm)

    alert = next(a for a in h.alerts if "already been reviewed" in a)
    assert "approved" in alert.lower()
    assert str(h.user_id) in alert  # the reviewer, since this harness self-reviews
    assert " at " in alert  # a timestamp is present, not just the outcome


async def test_the_approved_verdict_shows_amount_and_user_with_navigation(manual_harness):
    """The reviewer's own result screen -- not just the depositor's DM --
    must show what was credited and to whom, plus somewhere useful to go."""
    h = manual_harness
    approve = await _submit_manual(h)

    await h.press(approve)
    confirm = h.screen.callback_for("Yes, Approve")
    await h.press(confirm)

    verdict = next(s for s in h.session.screens if "APPROVED" in s.text)
    assert f"#{1}" in verdict.text or "request #1" in verdict.text.lower()
    assert str(h.user_id) in verdict.text
    assert "₹500.00" in verdict.text

    buttons = " ".join(verdict.buttons())
    assert "Pending Deposits" in buttons
    assert "Payment Management" in buttons
    assert "Main Menu" in buttons


async def test_a_stale_approve_tap_after_a_decline_reports_the_real_outcome(manual_harness):
    """Two reviewers, same payment: one declines while the other's Approve
    tap (from before either of them decided) is still live. The stale tap
    must report what actually happened -- declined -- never silently
    approve and never credit."""
    from app.services.wallet import WalletService

    h = manual_harness
    approve_confirm = await _submit_manual(h)  # the review card's own "Approve" button
    decline = h.posted_to(REVIEW_CHANNEL)[0].callback_for("Decline")

    await h.press(decline)
    await h.send("blurry screenshot")

    # The original "Approve" tap, captured before the decline, is now stale.
    await h.press(approve_confirm)

    alert = next(a for a in h.alerts if "already been reviewed" in a)
    assert "declined" in alert.lower()

    async with h.dispatcher.workflow_data["session_factory"]() as session:
        assert await WalletService(session).get_balance(h.user_id) == 0


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


async def test_the_declined_verdict_shows_amount_reason_and_navigation(manual_harness):
    """The reviewer's own result screen for a decline: amount, user
    reference and the reason they typed, plus somewhere useful to go --
    not just a bare 'DECLINED' line."""
    h = manual_harness
    await _submit_manual(h)
    decline = h.posted_to(REVIEW_CHANNEL)[0].callback_for("Decline")

    await h.press(decline)
    await h.send("amount does not match the screenshot")

    verdict = next(s for s in h.session.screens if "DECLINED" in s.text and "request #" in s.text.lower())
    assert str(h.user_id) in verdict.text
    assert "₹500.00" in verdict.text
    assert "amount does not match the screenshot" in verdict.text

    buttons = " ".join(verdict.buttons())
    assert "Pending Deposits" in buttons
    assert "Payment Management" in buttons
    assert "Main Menu" in buttons


async def test_declining_with_a_native_reply_threads_the_confirmation(manual_harness):
    """When the admin actually uses Telegram's Reply on the bot's own
    decline-reason prompt, the confirmation sent back must carry real
    ``reply_parameters`` pointing at that message -- never a fabricated
    HTML blockquote. See app/utils/quotes.py."""
    h = manual_harness
    await _submit_manual(h)
    decline = h.posted_to(REVIEW_CHANNEL)[0].callback_for("Decline")

    await h.press(decline)
    prompt_message_id = h.screen.payload.get("message_id") or 555

    await h.send("amount does not match the screenshot", reply_to_message_id=prompt_message_id)

    done = next(s for s in h.session.screens if s.text.startswith("❌ Request #"))
    reply_params = done.payload.get("reply_parameters")
    assert reply_params is not None
    assert reply_params["message_id"] == prompt_message_id
    assert "<blockquote>" not in done.text


async def test_declining_without_a_reply_sends_no_reply_parameters(manual_harness):
    """The common case -- the admin just types the reason, without using
    Reply -- must not fabricate a reply-to relationship that never existed."""
    h = manual_harness
    await _submit_manual(h)
    decline = h.posted_to(REVIEW_CHANNEL)[0].callback_for("Decline")

    await h.press(decline)
    await h.send("amount does not match the screenshot")

    done = next(s for s in h.session.screens if s.text.startswith("❌ Request #"))
    assert done.payload.get("reply_parameters") is None


async def test_declining_from_the_panel_also_closes_out_the_channel_copy(
    manual_harness, session_factory
):
    """Same regression as approve: declining via the panel must still close
    out the channel's copy of the review card, not just wherever the reason
    was typed."""
    from app.database.models import Payment

    h = manual_harness
    await _submit_manual(h)

    await h.send("/admin")
    await h.tap("Finance")
    await h.tap("Payments")
    await h.tap("Pending deposits")
    await h.tap("402199881122")
    await h.tap("Decline")
    await h.send("does not match")

    channel_posts = h.posted_to(REVIEW_CHANNEL)
    stripped = [s for s in channel_posts if s.method == "EditMessageReplyMarkup"]
    verdicts = [s for s in channel_posts if s.method == "SendMessage" and " by " in s.text]
    assert stripped, "the channel copy's buttons were never stripped"
    assert verdicts, "no verdict was ever posted to the channel"

    async with session_factory() as session:
        payment = await session.get(Payment, 1)
        assert stripped[0].payload["message_id"] == payment.review_message_id


async def test_a_reused_reference_is_rejected_at_submission(manual_harness):
    """Regression: the generic "already being processed" wording read like a
    fresh submission was accepted and awaiting review, when actually nothing
    new was created and no admin was ever going to see it. The message must
    say plainly that this reference was already used before."""
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

    assert "already been submitted" in h.text
    assert "already being processed" not in h.text
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
    await h.tap("Finance")
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
    await h.tap("Finance")
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
    assert posted[0].buttons() == ["Approve", "Decline"]

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


async def test_a_support_admin_can_resend_without_the_balance_permission(
    manual_harness, monkeypatch, settings
):
    """Resend only needs 'payments' -- but it used to finish by calling
    open_request, which required the stronger 'balance' permission SUPPORT
    lacks, so a successful resend was immediately followed by an access-denied
    error on the very screen meant to confirm it worked."""
    from aiogram.exceptions import TelegramBadRequest

    from app.bot.callbacks import ManualCB
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

    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")
    await h.tap("I Have Paid")
    await h.send("402199881122")
    await h.send_photo("screenshot-1")  # channel down: notification missing

    settings.admin_roles = {h.user_id: AdminRole.SUPPORT}  # payments, not balance
    blocked = False  # channel back up

    await h.press(ManualCB(action="resend", payment_id=1).pack())

    assert "do not have access" not in h.text
    assert len(h.posted_to(REVIEW_CHANNEL)) == 1


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
    await h.tap("Finance")
    await h.tap("Payments")
    await h.tap("Pending deposits")
    await h.tap("402199881122")

    assert "DEPOSIT REQUEST" in h.text
    assert h.screen.buttons() == ["Approve", "Decline"]


async def test_an_empty_queue_says_so(manual_harness):
    h = manual_harness
    await h.send("/start")
    await h.send("/admin")
    await h.tap("Finance")
    await h.tap("Payments")
    await h.tap("Pending deposits")

    assert "Nothing is waiting" in h.text


async def test_a_request_can_be_approved_from_the_panel(manual_harness, session_factory):
    """The channel post is convenience; the panel is the fallback that works."""
    from app.services.wallet import WalletService

    h = manual_harness
    await _submit_manual(h)

    await h.send("/admin")
    await h.tap("Finance")
    await h.tap("Payments")
    await h.tap("Pending deposits")
    await h.tap("402199881122")

    assert "DEPOSIT REQUEST" in h.text
    assert h.screen.buttons() == ["Approve", "Decline"]

    await h.tap("Approve")
    assert h.buttons() == ["Yes, Approve", "Cancel"]
    await h.tap("Yes, Approve")
    async with session_factory() as session:
        assert await WalletService(session).get_balance(h.user_id) == 50_000


async def test_approving_from_the_panel_also_closes_out_the_channel_copy(
    manual_harness, session_factory
):
    """Regression: approving from the admin panel used to strip/reply only on
    the panel's own message. The channel copy -- what anyone else reviewing
    payments actually looks at -- was left showing live Approve/Decline
    buttons forever on an already-settled payment, with no verdict at all."""
    from app.database.models import Payment

    h = manual_harness
    await _submit_manual(h)

    await h.send("/admin")
    await h.tap("Finance")
    await h.tap("Payments")
    await h.tap("Pending deposits")
    await h.tap("402199881122")
    await h.tap("Approve")
    await h.tap("Yes, Approve")

    channel_posts = h.posted_to(REVIEW_CHANNEL)
    stripped = [s for s in channel_posts if s.method == "EditMessageReplyMarkup"]
    verdicts = [s for s in channel_posts if s.method == "SendMessage" and " by " in s.text]
    assert stripped, "the channel copy's buttons were never stripped"
    assert verdicts, "no verdict was ever posted to the channel"

    async with session_factory() as session:
        payment = await session.get(Payment, 1)
        assert stripped[0].payload["message_id"] == payment.review_message_id


async def test_an_approved_request_leaves_the_queue(manual_harness):
    h = manual_harness
    await _submit_manual(h)

    approve = h.posted_to(REVIEW_CHANNEL)[0].callback_for("Approve")
    await h.press(approve)
    confirm = h.screen.callback_for("Yes, Approve")
    await h.press(confirm)

    await h.send("/admin")
    await h.tap("Finance")
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
