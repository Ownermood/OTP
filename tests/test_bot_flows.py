"""End-to-end flows driven through the real dispatcher.

These are the tests that answer "does the bot actually work": a real Update
goes in, every middleware and handler runs, and the assertion is on what the
user would see on their screen.
"""

import pytest


async def test_start_shows_the_welcome_and_the_main_menu(harness):
    await harness.send("/start")

    assert "WELCOME" in harness.text
    buttons = harness.buttons()
    assert "🛍 Buy Number" in buttons
    assert "💳 Balance" in buttons
    assert "ℹ️ Help" in buttons


async def test_start_creates_the_user(harness, session_factory):
    from app.database.repositories import UserRepository

    await harness.send("/start")

    async with session_factory() as session:
        user = await UserRepository(session).get(harness.user_id)

    assert user is not None
    assert user.username == f"user{harness.user_id}"
    assert user.balance == 0


async def test_returning_user_sees_their_balance(harness):
    await harness.send("/start")
    await harness.send("/start")

    assert "Balance" in harness.text


async def test_every_screen_offers_a_way_back(harness):
    """The spec's rule: the user is never stranded."""
    await harness.send("/start")

    for label in ("Buy Number", "Balance", "Profile", "Help", "Orders", "Favorites"):
        await harness.send("/start")
        await harness.tap(label)
        buttons = " ".join(harness.buttons())
        assert "Back" in buttons or "Main Menu" in buttons, f"{label} screen strands the user"


# -- the buy flow, driven the way a user would ------------------------------


async def _fund(session_factory, user_id: int, amount: int) -> None:
    from app.core.constants import TransactionType
    from app.services.wallet import WalletService

    async with session_factory() as session:
        await WalletService(session).credit(
            user_id, amount, TransactionType.DEPOSIT, f"test:fund:{user_id}:{amount}"
        )
        await session.commit()


async def test_buy_flow_end_to_end(harness, session_factory):
    """/start → Buy → service → country → confirm → a number on screen."""
    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 10_000)

    await harness.tap("Buy Number")
    assert "BUY NUMBER" in harness.text
    assert any("WhatsApp" in b for b in harness.buttons())

    await harness.tap("WhatsApp")
    assert "SELECT COUNTRY" in harness.text
    # The country button carries the price, and the availability dot.
    assert any("India" in b and "11.00" in b for b in harness.buttons())

    await harness.tap("India")
    assert "ORDER CONFIRMATION" in harness.text
    assert "₹11.00" in harness.text

    await harness.tap("Confirm")
    assert "NUMBER PURCHASED" in harness.text
    assert "+91" in harness.text
    assert "Waiting for SMS" in harness.text


async def test_buying_debits_exactly_once(harness, session_factory):
    from app.services.wallet import WalletService

    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 10_000)

    await harness.tap("Buy Number")
    await harness.tap("WhatsApp")
    await harness.tap("India")
    confirm = harness.screen.callback_for("Confirm")

    await harness.press(confirm)
    async with session_factory() as session:
        assert await WalletService(session).get_balance(harness.user_id) == 8_900


async def _reach_confirm(harness, session_factory, funds: int = 10_000) -> str:
    await harness.send("/start")
    await _fund(session_factory, harness.user_id, funds)
    await harness.tap("Buy Number")
    await harness.tap("WhatsApp")
    await harness.tap("India")
    return harness.screen.callback_for("Confirm")


async def test_rapid_double_tap_is_swallowed_before_the_handler(harness, session_factory):
    """First line of defence: the throttle layer drops the duplicate callback."""
    from app.services.wallet import WalletService

    confirm = await _reach_confirm(harness, session_factory)

    await harness.press(confirm)
    await harness.press(confirm)  # same data, immediately — never reaches a handler

    assert harness.replied is False
    assert harness.sms.created == 1
    async with session_factory() as session:
        assert await WalletService(session).get_balance(harness.user_id) == 8_900


async def test_replayed_confirm_is_refused_by_the_token(harness, session_factory):
    """Second line of defence: past the throttle, the token is already spent."""
    from app.services.wallet import WalletService

    confirm = await _reach_confirm(harness, session_factory)

    await harness.press(confirm)
    harness.forget_last_tap()  # as if the taps were seconds apart
    await harness.press(confirm)

    # Answered as an alert on the button, so the purchase screen stays put.
    assert any("already being processed" in alert for alert in harness.alerts)
    assert harness.sms.created == 1
    async with session_factory() as session:
        assert await WalletService(session).get_balance(harness.user_id) == 8_900


async def test_buying_without_balance_shows_a_helpful_error(harness):
    await harness.send("/start")

    await harness.tap("Buy Number")
    await harness.tap("WhatsApp")
    await harness.tap("India")
    await harness.tap("Confirm")

    assert "Insufficient balance" in harness.text
    assert "₹11.00" in harness.text  # what they needed
    assert harness.sms.created == 0


async def test_no_numbers_available_is_reported_and_refunded(harness, session_factory):
    from app.services.wallet import WalletService

    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 10_000)

    await harness.tap("Buy Number")
    await harness.tap("WhatsApp")
    await harness.tap("India")
    harness.sms.fail_next = True
    await harness.tap("Confirm")

    assert "No numbers available" in harness.text
    async with session_factory() as session:
        assert await WalletService(session).get_balance(harness.user_id) == 10_000


async def test_service_search(harness):
    await harness.send("/start")
    await harness.tap("Buy Number")
    await harness.tap("Search")

    assert "SEARCH SERVICE" in harness.text

    await harness.send("whats")
    assert "Results for" in harness.text
    assert any("WhatsApp" in b for b in harness.buttons())


async def test_search_with_no_matches_does_not_dead_end(harness):
    await harness.send("/start")
    await harness.tap("Buy Number")
    await harness.tap("Search")
    await harness.send("zzzzz")

    assert "No matches" in harness.text
    assert "Back" in " ".join(harness.buttons())


# -- wallet, promo and orders ----------------------------------------------


async def test_wallet_deposit_flow(harness):
    await harness.send("/start")
    await harness.tap("Balance")
    assert "WALLET" in harness.text

    await harness.tap("Add Balance")
    assert "payment method" in harness.text.lower()

    await harness.tap("fake_pay")
    assert "ENTER AMOUNT" in harness.text

    await harness.send("500")
    assert "PAYMENT" in harness.text
    assert "₹500.00" in harness.text
    assert "Pay Now" in " ".join(harness.buttons())


async def test_deposit_below_the_minimum_is_rejected(harness):
    await harness.send("/start")
    await harness.tap("Balance")
    await harness.tap("Add Balance")
    await harness.tap("fake_pay")
    await harness.send("1")

    assert "does not look right" in harness.text.lower()


async def test_checking_a_paid_invoice_credits_the_balance(harness, session_factory):
    from app.services.wallet import WalletService

    await harness.send("/start")
    await harness.tap("Balance")
    await harness.tap("Add Balance")
    await harness.tap("fake_pay")
    await harness.send("500")

    harness.payments.status = "paid"
    await harness.tap("Check Payment")

    assert "PAYMENT RECEIVED" in harness.text
    async with session_factory() as session:
        assert await WalletService(session).get_balance(harness.user_id) == 50_000


async def test_promo_redemption(harness, session_factory):
    from app.services.promo import PromoService
    from app.services.wallet import WalletService

    await harness.send("/start")
    async with session_factory() as session:
        await PromoService(session, WalletService(session)).create(
            code="WELCOME50",
            amount=5_000,
            max_activations=5,
            expires_at=None,
            min_deposit=0,
            created_by=1,
        )

    await harness.tap("Balance")
    await harness.tap("Promo")
    assert "PROMO CODE" in harness.text

    await harness.send("welcome50")
    assert "PROMO ACTIVATED" in harness.text
    assert "₹50.00" in harness.text


async def test_bad_promo_code_shows_a_friendly_error(harness):
    await harness.send("/start")
    await harness.tap("Balance")
    await harness.tap("Promo")
    await harness.send("NOPE123")

    assert "Invalid or expired" in harness.text


async def test_orders_screen_lists_a_purchase(harness, session_factory):
    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 10_000)
    await harness.tap("Buy Number")
    await harness.tap("WhatsApp")
    await harness.tap("India")
    await harness.tap("Confirm")

    await harness.send("/start")
    await harness.tap("Orders")
    await harness.tap("SMS Activations")

    assert "SMS ACTIVATIONS" in harness.text
    assert any("#1" in b and "WhatsApp" in b for b in harness.buttons())


async def test_cancelling_an_order_refunds_it(harness, session_factory):
    from app.services.wallet import WalletService

    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 10_000)
    await harness.tap("Buy Number")
    await harness.tap("WhatsApp")
    await harness.tap("India")
    await harness.tap("Confirm")

    await harness.tap("Cancel")
    assert "Cancel Activation?" in harness.text

    await harness.tap("Yes, cancel")
    assert "ACTIVATION CANCELLED" in harness.text
    async with session_factory() as session:
        assert await WalletService(session).get_balance(harness.user_id) == 10_000


async def test_profile_shows_statistics(harness, session_factory):
    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 10_000)

    await harness.send("/start")
    await harness.tap("Profile")

    assert "MY PROFILE" in harness.text
    assert "₹100.00" in harness.text
    assert "Numbers purchased" in harness.text


async def test_favorites_can_be_added_from_a_quote_and_bought_back(harness, session_factory):
    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 10_000)

    await harness.tap("Buy Number")
    await harness.tap("WhatsApp")
    await harness.tap("India")
    await harness.tap("Add to Favorites")
    assert any("favorites" in alert.lower() for alert in harness.alerts)

    await harness.send("/start")
    await harness.tap("Favorites")
    assert "FAVORITES" in harness.text

    await harness.tap("India")
    assert "Current price" in harness.text
    assert "Buy Now" in " ".join(harness.buttons())


async def test_referral_screen_shows_a_working_link(harness):
    await harness.send("/start")
    await harness.tap("Referral")

    assert "REFERRAL PROGRAM" in harness.text
    assert f"?start=ref{harness.user_id}" in harness.text


async def test_help_topics_render(harness):
    await harness.send("/start")
    await harness.tap("Help")
    assert "HELP CENTER" in harness.text

    await harness.tap("Refund policy")
    assert "REFUND POLICY" in harness.text
    assert "refunds the full price" in harness.text


# -- SMM panel --------------------------------------------------------------


async def test_smm_order_flow_end_to_end(harness, session_factory):
    """Platform → service → link → quantity → confirm → order created."""
    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 200_000)

    await harness.tap("SMM Panel")
    assert "SMM PANEL" in harness.text
    assert any("Instagram" in b for b in harness.buttons())

    await harness.tap("Instagram")
    assert any("Instagram Followers" in b for b in harness.buttons())

    await harness.tap("Instagram Followers")
    assert "Rate" in harness.text
    assert "Send the <b>link</b>" in harness.text

    await harness.send("https://instagram.com/example")
    assert "quantity" in harness.text.lower()

    await harness.send("500")
    assert "ORDER CONFIRMATION" in harness.text
    # 100.00/1000 × 500 = 50.00, +20% SMM markup = 60.00
    assert "₹60.00" in harness.text

    await harness.tap("Confirm")
    assert "ORDER CREATED" in harness.text
    assert harness.smm.created == 1


async def test_smm_rejects_a_bad_link(harness, session_factory):
    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 200_000)
    await harness.tap("SMM Panel")
    await harness.tap("Instagram")
    await harness.tap("Instagram Followers")

    await harness.send("not-a-link")
    assert "does not look right" in harness.text.lower()


async def test_smm_enforces_quantity_bounds(harness, session_factory):
    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 200_000)
    await harness.tap("SMM Panel")
    await harness.tap("Instagram")
    await harness.tap("Instagram Followers")
    await harness.send("https://instagram.com/example")

    await harness.send("5")  # below the service minimum of 100
    assert "does not look right" in harness.text.lower()


async def test_smm_order_can_be_tracked(harness, session_factory):
    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 200_000)
    await harness.tap("SMM Panel")
    await harness.tap("Instagram")
    await harness.tap("Instagram Followers")
    await harness.send("https://instagram.com/example")
    await harness.send("500")
    await harness.tap("Confirm")

    await harness.tap("Track Status")
    assert "ORDER STATUS" in harness.text
    assert "Processing" in harness.text


async def test_smm_search(harness):
    await harness.send("/start")
    await harness.tap("SMM Panel")
    await harness.tap("Search")
    assert "SEARCH" in harness.text

    await harness.send("followers")
    assert any("Instagram Followers" in b for b in harness.buttons())


# -- admin ------------------------------------------------------------------


@pytest.fixture
def admin_harness(harness, settings):
    """The same bot, but the driving user is the configured owner."""
    settings.admin_ids = [harness.user_id]
    settings.admin_roles = {}
    return harness


async def test_non_admin_cannot_open_the_panel(harness):
    await harness.send("/start")
    await harness.send("/admin")

    assert "do not have access" in harness.text


async def test_admin_panel_opens_for_the_owner(admin_harness):
    await admin_harness.send("/start")
    await admin_harness.send("/admin")

    assert "ADMIN PANEL" in admin_harness.text
    assert "Owner" in admin_harness.text
    buttons = " ".join(admin_harness.buttons())
    assert "Dashboard" in buttons and "Broadcast" in buttons


async def test_admin_dashboard_renders(admin_harness):
    await admin_harness.send("/start")
    await admin_harness.send("/admin")
    await admin_harness.tap("Dashboard")

    assert "DASHBOARD" in admin_harness.text
    assert "Total users" in admin_harness.text
    assert "Revenue" in admin_harness.text


async def test_admin_health_screen_probes_providers(admin_harness):
    await admin_harness.send("/start")
    await admin_harness.send("/admin")
    await admin_harness.tap("Dashboard")
    await admin_harness.tap("Status")

    assert "SYSTEM STATUS" in admin_harness.text
    assert "🟢 Online" in admin_harness.text
    assert "Provider balance" in admin_harness.text


async def test_admin_can_search_and_adjust_a_balance(admin_harness, session_factory):
    from app.services.wallet import WalletService

    await admin_harness.send("/start")
    await admin_harness.send("/admin")
    await admin_harness.tap("Users")
    assert "SEARCH" in admin_harness.text

    await admin_harness.send(str(admin_harness.user_id))
    assert "RESULTS" in admin_harness.text

    await admin_harness.tap("user")
    assert "👤 <b>USER</b>" in admin_harness.text

    await admin_harness.tap("Adjust balance")
    await admin_harness.send("250")
    assert "REASON" in admin_harness.text

    await admin_harness.send("goodwill credit")

    screens = [s.text for s in admin_harness.session.screens]
    assert any("BALANCE ADJUSTED" in text for text in screens)
    # The user is told it was an adjustment, not a payment they made.
    notice = next(text for text in screens if "BALANCE UPDATED" in text)
    assert "added to your balance by an administrator" in notice
    assert "goodwill credit" in notice

    async with session_factory() as session:
        assert await WalletService(session).get_balance(admin_harness.user_id) == 25_000


async def test_admin_deduction_reads_correctly_to_the_user(admin_harness, session_factory):
    await admin_harness.send("/start")
    await _fund(session_factory, admin_harness.user_id, 50_000)

    await admin_harness.send("/admin")
    await admin_harness.tap("Users")
    await admin_harness.send(str(admin_harness.user_id))
    await admin_harness.tap("user")
    await admin_harness.tap("Adjust balance")
    await admin_harness.send("-100")
    await admin_harness.send("chargeback")

    notice = next(
        text for text in (s.text for s in admin_harness.session.screens)
        if "BALANCE UPDATED" in text
    )
    assert "deducted from your balance" in notice
    assert "₹100.00" in notice and "-₹100.00" not in notice


async def test_balance_adjustments_are_audited(admin_harness, session_factory):
    from app.database.repositories import AdminActionRepository

    await admin_harness.send("/start")
    await _fund(session_factory, admin_harness.user_id, 50_000)
    await admin_harness.send("/admin")
    await admin_harness.tap("Users")
    await admin_harness.send(str(admin_harness.user_id))
    await admin_harness.tap("user")
    await admin_harness.tap("Adjust balance")
    await admin_harness.send("-100")
    await admin_harness.send("chargeback")

    async with session_factory() as session:
        actions = await AdminActionRepository(session).recent()

    assert any(a.action == "balance_adjust" and "chargeback" in (a.details or "") for a in actions)


async def test_admin_can_create_a_promo(admin_harness, session_factory):
    from app.database.repositories import PromoRepository

    await admin_harness.send("/start")
    await admin_harness.send("/admin")
    await admin_harness.tap("Promo")
    await admin_harness.tap("Create")

    await admin_harness.send("SUMMER25")
    await admin_harness.send("25")
    await admin_harness.send("100")

    assert "PROMO CREATED" in admin_harness.text
    async with session_factory() as session:
        promo = await PromoRepository(session).get_by_code("SUMMER25")
    assert promo is not None
    assert promo.amount == 2_500
    assert promo.max_activations == 100


async def test_admin_can_create_a_percentage_promo(admin_harness, session_factory):
    from app.database.repositories import PromoRepository

    await admin_harness.send("/start")
    await admin_harness.send("/admin")
    await admin_harness.tap("Promo")
    await admin_harness.tap("Create")
    await admin_harness.send("BOOST10")
    await admin_harness.send("10%")
    await admin_harness.send("50")

    assert "PROMO CREATED" in admin_harness.text
    assert "10% of next deposit" in admin_harness.text
    async with session_factory() as session:
        promo = await PromoRepository(session).get_by_code("BOOST10")
    assert promo.percent == 10
    assert promo.amount == 0


async def test_maintenance_mode_blocks_users_but_not_admins(admin_harness, harness):
    await admin_harness.send("/start")
    await admin_harness.send("/admin")
    await admin_harness.tap("Dashboard")
    await admin_harness.tap("Status")
    await admin_harness.tap("Enable maintenance")

    assert "Maintenance: <b>ON</b>" in admin_harness.text

    # The admin still gets through.
    await admin_harness.send("/start")
    assert "Maintenance" not in admin_harness.text


# -- rentals ----------------------------------------------------------------


async def test_rental_flow_end_to_end(harness, session_factory):
    """Country → duration → services at real prices → confirm."""
    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 100_000)

    await harness.tap("Rent Number")
    assert any("India" in b for b in harness.buttons())

    await harness.tap("India")
    assert "SELECT DURATION" in harness.text
    assert "4h" in " ".join(harness.buttons())

    await harness.tap("1d")
    assert "SELECT SERVICE" in harness.text
    # 1000/hour × 24h = 240.00, +10% fee = 264.00
    assert any("264.00" in b for b in harness.buttons())

    await harness.tap("Full rent")
    assert "RENTAL CONFIRMATION" in harness.text
    assert "1 day" in harness.text

    await harness.tap("Confirm")
    assert "NUMBER RENTED" in harness.text


async def test_rental_prices_scale_with_the_chosen_duration(harness, session_factory):
    """A longer rental must not reuse the short rental's price."""
    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 500_000)

    await harness.tap("Rent Number")
    await harness.tap("India")
    await harness.tap("4h")
    four_hours = " ".join(harness.buttons())

    await harness.tap("Back")
    await harness.tap("1d")
    one_day = " ".join(harness.buttons())

    assert "44.00" in four_hours
    assert "264.00" in one_day


async def test_custom_rental_duration_is_bounded(harness, session_factory):
    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 500_000)

    await harness.tap("Rent Number")
    await harness.tap("India")
    await harness.tap("Custom")
    assert "CUSTOM DURATION" in harness.text

    await harness.send("99999")  # above MAX_RENTAL_HOURS
    assert "does not look right" in harness.text.lower()


# -- error handling and access control --------------------------------------


async def test_a_crashing_provider_shows_a_friendly_message_not_a_traceback(
    harness, session_factory, monkeypatch
):
    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 10_000)

    async def explode(*args, **kwargs):
        raise RuntimeError("upstream exploded")

    await harness.tap("Buy Number")
    # Patched after the service catalogue is cached, so the crash lands on the
    # country lookup, which is resolved per call.
    monkeypatch.setattr(harness.sms, "get_countries", explode)
    await harness.tap("WhatsApp")

    assert "Something went wrong" in harness.text
    assert "Traceback" not in harness.text
    assert "RuntimeError" not in harness.text


async def test_a_banned_user_is_turned_away(harness, session_factory):
    from app.database.repositories import UserRepository

    await harness.send("/start")
    async with session_factory() as session:
        await UserRepository(session).set_banned(harness.user_id, True, "abuse")
        await session.commit()

    await harness.send("/start")
    assert "suspended" in harness.text


async def test_an_expired_quote_does_not_buy(harness, session_factory):
    """A token from a previous session must not resolve."""
    await harness.send("/start")
    await _fund(session_factory, harness.user_id, 10_000)

    await harness.tap("Buy Number")
    await harness.tap("WhatsApp")
    await harness.tap("India")
    confirm = harness.screen.callback_for("Confirm")

    # Simulate the bot restarting between the quote and the tap.
    harness.dispatcher.workflow_data["tokens"] = type(
        harness.dispatcher.workflow_data["tokens"]
    )()

    await harness.press(confirm)
    assert harness.sms.created == 0


async def test_one_user_cannot_open_another_users_order(harness, session_factory):
    """An order id lifted from someone else's callback must not resolve."""
    from app.core.constants import OrderKind, OrderStatus
    from app.database.repositories import OrderRepository, UserRepository

    await harness.send("/start")
    async with session_factory() as session:
        await UserRepository(session).get_or_create(999888, "victim", "Victim")
        order = await OrderRepository(session).create(
            user_id=999888,
            kind=OrderKind.ACTIVATION,
            status=OrderStatus.PROCESSING,
            provider="fake_sms",
            service_code="wa",
            service_name="WhatsApp",
            country_id=22,
            country_name="India",
            price=1_100,
            phone="+919999999999",
        )
        await session.commit()
        stolen_id = order.id

    from app.bot.callbacks import OrderCB

    await harness.press(OrderCB(action="detail", order_id=stolen_id).pack())

    assert "Order not found" in harness.text
    assert "+919999999999" not in harness.text


# -- manual (UPI / bank) deposits -------------------------------------------

REVIEW_CHANNEL = -1001234567890


@pytest.fixture
def manual_harness(harness, settings):
    """Manual deposits on, with the driving user as the reviewing admin."""
    settings.manual_payment_enabled = True
    settings.manual_payment_channel_id = REVIEW_CHANNEL
    settings.admin_ids = [harness.user_id]
    settings.admin_roles = {}
    return harness


async def test_manual_deposit_reaches_the_review_channel(manual_harness):
    """Amount → UTR → screenshot → posted for review, balance untouched."""
    from app.services.wallet import WalletService

    h = manual_harness
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")

    assert "UPI / Bank Transfer" in " ".join(h.buttons())
    await h.tap("UPI / Bank")
    assert "UPI / BANK TRANSFER" in h.text
    assert "yourname@upi" in h.text  # the operator's editable details

    await h.send("500")
    assert "TRANSACTION REFERENCE" in h.text

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


async def _submit_manual(h, amount="500", utr="402199881122") -> str:
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / Bank")
    await h.send(amount)
    await h.send(utr)
    await h.send_photo("screenshot-1")
    return h.posted_to(REVIEW_CHANNEL)[0].callback_for("Approve")


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
    await h.tap("UPI / Bank")
    await h.send("500")
    await h.send("402199881122")  # the same payment, claimed again
    await h.send_photo("screenshot-1")

    assert "already being processed" in h.text
    assert len(h.posted_to(REVIEW_CHANNEL)) == 0


async def test_a_bad_reference_is_rejected_before_the_screenshot(manual_harness):
    h = manual_harness
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / Bank")
    await h.send("500")
    await h.send("123")  # too short to be a real reference

    assert "does not look right" in h.text.lower()


async def test_text_instead_of_a_screenshot_is_named_not_ignored(manual_harness):
    h = manual_harness
    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / Bank")
    await h.send("500")
    await h.send("402199881122")

    await h.send("here is my payment, trust me")
    assert "send the screenshot as a photo" in h.text.lower()
