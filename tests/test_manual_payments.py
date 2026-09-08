"""Manually reviewed deposits.

The guarantee under test: money moves on approval and at no other moment, and
one real payment can be claimed exactly once.
"""

import pytest

from app.core.constants import PaymentStatus
from app.core.exceptions import (
    AccessDeniedError,
    DuplicateOperationError,
    ValidationError,
)
from app.services.manual_payments import ManualPaymentService, normalise_utr
from app.services.payments import PaymentService
from app.services.referrals import ReferralService


@pytest.fixture
def manual(session, wallet, settings) -> ManualPaymentService:
    settings.manual_payment_enabled = True
    settings.manual_payment_channel_id = -1001234567890
    settings.admin_ids = [1]
    settings.admin_roles = {}
    payments = PaymentService(
        session, {}, wallet, ReferralService(session, wallet, settings), settings
    )
    return ManualPaymentService(session, payments, settings)


ADMIN = 1
OUTSIDER = 4242


# -- reference validation ---------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("123456789012", "123456789012"),
        ("  ab12cd34  ", "AB12CD34"),
        ("4021-9988-1122", "402199881122"),
    ],
)
def test_references_are_normalised(raw, expected):
    assert normalise_utr(raw) == expected


@pytest.mark.parametrize("raw", ["", "123", "x" * 40, "has space!", "@@@@@@"])
def test_bad_references_are_rejected(raw):
    with pytest.raises(ValidationError):
        normalise_utr(raw)


def test_case_cannot_disguise_a_reused_reference():
    assert normalise_utr("ab12cd34") == normalise_utr("AB12CD34")


# -- submission -------------------------------------------------------------


async def test_submitting_does_not_touch_the_balance(manual, user, wallet):
    """The whole point: nothing moves until a human approves."""
    payment = await manual.submit(user.id, 50_000, "UTR000111222", "file-1")

    assert payment.status == PaymentStatus.PENDING
    assert payment.amount == 50_000
    assert (await wallet.get_balance(user.id)) == 10_000  # unchanged


async def test_the_same_reference_cannot_be_submitted_twice(manual, user):
    """A screenshot of one real payment must not fund two deposits."""
    await manual.submit(user.id, 50_000, "UTR000111222", "file-1")

    with pytest.raises(DuplicateOperationError):
        await manual.submit(user.id, 50_000, "UTR000111222", "file-2")


async def test_a_reference_cannot_be_reused_by_another_user(session, manual, user):
    """The obvious fraud: forwarding someone else's screenshot."""
    from app.database.models import User

    session.add(User(id=7777, username="second", balance=0))
    await session.commit()

    await manual.submit(user.id, 50_000, "UTR000111222", "file-1")

    with pytest.raises(DuplicateOperationError):
        await manual.submit(7777, 50_000, "UTR000111222", "file-1")


async def test_a_user_cannot_flood_the_review_queue(manual, user, settings):
    settings.manual_payment_max_pending = 2

    await manual.submit(user.id, 50_000, "UTR000000001", "f1")
    await manual.submit(user.id, 50_000, "UTR000000002", "f2")

    with pytest.raises(ValidationError):
        await manual.submit(user.id, 50_000, "UTR000000003", "f3")


async def test_amount_bounds_apply(manual, user):
    with pytest.raises(ValidationError):
        await manual.submit(user.id, 1, "UTR000000001", "f1")
    with pytest.raises(ValidationError):
        await manual.submit(user.id, 999_999_999, "UTR000000002", "f2")


async def test_a_declined_reference_frees_nothing(manual, user):
    """A declined request still holds its reference, so it cannot be retried."""
    payment = await manual.submit(user.id, 50_000, "UTR000111222", "file-1")
    await manual.decline(payment.id, ADMIN, "amount mismatch")

    with pytest.raises(DuplicateOperationError):
        await manual.submit(user.id, 50_000, "UTR000111222", "file-1")


# -- authorisation ----------------------------------------------------------


async def test_only_a_configured_reviewer_can_approve(manual, user, wallet):
    """The buttons are visible in a channel; the permission is not in the tap."""
    payment = await manual.submit(user.id, 50_000, "UTR000111222", "file-1")

    with pytest.raises(AccessDeniedError):
        await manual.approve(payment.id, OUTSIDER)

    assert (await wallet.get_balance(user.id)) == 10_000


async def test_only_a_configured_reviewer_can_decline(manual, user):
    payment = await manual.submit(user.id, 50_000, "UTR000111222", "file-1")

    with pytest.raises(AccessDeniedError):
        await manual.decline(payment.id, OUTSIDER, "nope")


async def test_reviewing_needs_the_balance_permission_not_just_payments(
    manual, user, settings, wallet
):
    """Approving creates money, so a read-only support role must not do it."""
    from app.core.constants import AdminRole

    settings.admin_ids = [1, 98, 99]
    settings.admin_roles = {98: AdminRole.FINANCE, 99: AdminRole.SUPPORT}

    assert manual.can_review(98) is True   # finance adjusts balances
    assert manual.can_review(99) is False  # support only reads
    assert manual.can_review(OUTSIDER) is False

    payment = await manual.submit(user.id, 50_000, "UTR000111222", "file-1")
    with pytest.raises(AccessDeniedError):
        await manual.approve(payment.id, 99)

    assert (await wallet.get_balance(user.id)) == 10_000


async def test_a_viewer_cannot_review(manual, settings):
    from app.core.constants import AdminRole

    settings.admin_ids = [1, 97]
    settings.admin_roles = {97: AdminRole.VIEWER}
    assert manual.can_review(97) is False


# -- approval ---------------------------------------------------------------


async def test_approval_credits_the_balance(manual, user, wallet):
    payment = await manual.submit(user.id, 50_000, "UTR000111222", "file-1")

    decision = await manual.approve(payment.id, ADMIN)

    assert decision.approved is True
    assert decision.applied is True
    assert decision.balance_after == 60_000
    assert (await wallet.get_balance(user.id)) == 60_000
    assert payment.status == PaymentStatus.PAID
    assert payment.reviewed_by == ADMIN


async def test_approving_twice_credits_once(manual, user, wallet):
    """Two reviewers tapping Approve on the same post."""
    payment = await manual.submit(user.id, 50_000, "UTR000111222", "file-1")

    first = await manual.approve(payment.id, ADMIN)
    second = await manual.approve(payment.id, ADMIN)

    assert first.applied is True
    assert second.applied is False
    assert (await wallet.get_balance(user.id)) == 60_000


async def test_an_approved_request_cannot_then_be_declined(manual, user, wallet):
    payment = await manual.submit(user.id, 50_000, "UTR000111222", "file-1")
    await manual.approve(payment.id, ADMIN)

    decision = await manual.decline(payment.id, ADMIN, "changed my mind")

    assert decision.applied is False
    assert payment.status == PaymentStatus.PAID
    assert (await wallet.get_balance(user.id)) == 60_000


async def test_a_declined_request_cannot_then_be_approved(manual, user, wallet):
    payment = await manual.submit(user.id, 50_000, "UTR000111222", "file-1")
    await manual.decline(payment.id, ADMIN, "fake screenshot")

    decision = await manual.approve(payment.id, ADMIN)

    assert decision.applied is False
    assert (await wallet.get_balance(user.id)) == 10_000


async def test_declining_moves_no_money_and_keeps_the_reason(manual, user, wallet):
    payment = await manual.submit(user.id, 50_000, "UTR000111222", "file-1")

    decision = await manual.decline(payment.id, ADMIN, "amount does not match")

    assert decision.approved is False
    assert payment.status == PaymentStatus.FAILED
    assert payment.review_note == "amount does not match"
    assert (await wallet.get_balance(user.id)) == 10_000


async def test_both_decisions_are_audited(session, manual, user):
    from app.database.repositories import AdminActionRepository

    approved = await manual.submit(user.id, 50_000, "UTR000000001", "f1")
    declined = await manual.submit(user.id, 20_000, "UTR000000002", "f2")

    await manual.approve(approved.id, ADMIN)
    await manual.decline(declined.id, ADMIN, "unreadable")

    actions = await AdminActionRepository(session).recent()
    by_action = {a.action: a for a in actions}

    assert "payment_approve" in by_action
    assert "UTR000000001" in by_action["payment_approve"].details
    assert "payment_decline" in by_action
    assert "unreadable" in by_action["payment_decline"].details


async def test_approval_pays_referral_commission(session, manual, user, wallet, settings):
    from app.database.models import User

    inviter = User(id=8888, username="inviter", balance=0)
    session.add(inviter)
    await session.commit()

    referrals = ReferralService(session, wallet, settings)
    await referrals.link(inviter.id, user.id)
    await session.commit()

    payment = await manual.submit(user.id, 10_000, "UTR000111222", "file-1")
    await manual.approve(payment.id, ADMIN)

    # REFERRAL_PERCENT defaults to 10%.
    assert (await wallet.get_balance(inviter.id)) == 1_000


async def test_manual_requests_are_never_auto_expired(session, manual, user):
    """A request waits for a human, not a clock."""
    from datetime import datetime, timedelta

    payment = await manual.submit(user.id, 50_000, "UTR000111222", "file-1")
    payment.expires_at = datetime.utcnow() - timedelta(days=365)
    await session.commit()

    assert await manual._payments.expire_stale() == 0
    await session.refresh(payment)
    assert payment.status == PaymentStatus.PENDING


async def test_disabled_module_refuses_submissions(manual, user, settings):
    settings.manual_payment_enabled = False

    with pytest.raises(ValidationError):
        await manual.submit(user.id, 50_000, "UTR000111222", "file-1")
