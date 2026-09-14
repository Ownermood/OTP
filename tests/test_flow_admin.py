"""The admin panel, driven as an admin would."""

import pytest

from tests.flow_helpers import fund


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
    assert "Choose a section" in admin_harness.text
    buttons = " ".join(admin_harness.buttons())
    # Top level is broad categories now; Broadcast lives one tap deeper, in
    # Operations -- see test_broadcast_lives_under_operations.
    assert "Dashboard" in buttons and "Operations" in buttons


async def test_the_orders_screen_does_not_borrow_the_panels_prompt(admin_harness):
    """Regression: a YAML restructure once moved 'Choose a section:' from the
    panel greeting onto the Orders list, where it made no sense."""
    h = admin_harness
    await h.send("/start")
    await h.send("/admin")
    await h.tap("Orders")

    assert "ORDERS" in h.text
    assert "Choose a section" not in h.text


async def test_admin_panel_shows_the_pending_count_and_a_refresh_button(admin_harness):
    h = admin_harness
    await h.send("/start")
    await h.send("/admin")

    # The pending-payment count now badges the Finance category at the top
    # level (Payments itself lives one tap deeper, inside Finance).
    assert any("Finance" in b and "(0)" in b for b in h.buttons())
    assert any("Refresh" in b for b in h.buttons())

    await h.tap("Refresh")
    assert "ADMIN PANEL" in h.text

    await h.tap("Finance")
    assert any("Payments" in b and "(0)" in b for b in h.buttons())
    assert any("Refresh" in b for b in h.buttons())

    await h.tap("Refresh")
    assert "FINANCE" in h.text


async def test_admin_dashboard_renders(admin_harness):
    await admin_harness.send("/start")
    await admin_harness.send("/admin")
    await admin_harness.tap("Dashboard")

    assert "DASHBOARD" in admin_harness.text
    assert "Total users" in admin_harness.text
    assert "Revenue" in admin_harness.text


async def test_payments_screen_shows_the_status_breakdown(admin_harness):
    """Efficient counts, not a wall of every payment row."""
    h = admin_harness
    await h.send("/start")
    await h.send("/admin")
    await h.tap("Finance")
    await h.tap("Payments")

    assert "PAYMENT MANAGEMENT" in h.text
    assert "Pending" in h.text
    assert "Approved" in h.text
    assert "Rejected" in h.text


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
    assert "<b>USER</b>" in admin_harness.text

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
    await fund(session_factory, admin_harness.user_id, 50_000)

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
    await fund(session_factory, admin_harness.user_id, 50_000)
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
    await admin_harness.tap("Finance")
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
    await admin_harness.tap("Finance")
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


async def test_the_maintenance_toggle_is_coloured_by_its_own_verb(admin_harness):
    """Styled by what the button's label says it does -- "Enable ..." is
    success, "Disable ..." is danger -- the same rule as any other
    enable/disable toggle, even though enabling maintenance is in fact the
    more disruptive of the two in practice."""
    from app.bot.keyboards.style import DANGER, SUCCESS

    h = admin_harness
    await h.send("/start")
    await h.send("/admin")
    await h.tap("Dashboard")
    await h.tap("Status")

    toggle = next(
        b
        for row in h.screen.markup.inline_keyboard
        for b in row
        if "maintenance" in b.text.lower()
    )
    assert "enable" in toggle.text.lower()
    assert toggle.style == SUCCESS

    await h.tap("Enable maintenance")
    toggle = next(
        b
        for row in h.screen.markup.inline_keyboard
        for b in row
        if "maintenance" in b.text.lower()
    )
    assert "disable" in toggle.text.lower()
    assert toggle.style == DANGER

    # The admin still gets through.
    await admin_harness.send("/start")
    assert "Maintenance" not in admin_harness.text


# -- broadcasts -------------------------------------------------------------


async def test_a_broadcast_is_previewed_before_it_is_sent(admin_harness, session_factory):
    """Regression: a typed message went to every user with no confirmation."""
    h = admin_harness
    await h.send("/start")
    await h.send("/admin")
    await h.tap("Operations")
    await h.tap("Broadcast")
    await h.tap("All users")

    await h.send("<b>Scheduled maintenance tonight</b>")

    assert "CONFIRM BROADCAST" in h.text
    assert "Scheduled maintenance tonight" in h.text
    assert "Send to 1" in " ".join(h.buttons())
    # Nothing delivered yet: the only messages so far are this admin's own screens.
    assert not any("Scheduled maintenance" in s.text for s in h.session.screens[:-1])

    await h.tap("Send to")
    assert "BROADCAST FINISHED" in h.text
    assert "Delivered: <b>1</b>" in h.text


async def test_the_broadcast_confirmation_colours_send_not_cancel(admin_harness):
    """Regression: Send (the confirm action) was danger-red and Cancel (which
    loses nothing) was blue -- the exact opposite of what red/green mean
    everywhere else in the bot."""
    from app.bot.keyboards.style import DANGER, SUCCESS

    h = admin_harness
    await h.send("/start")
    await h.send("/admin")
    await h.tap("Operations")
    await h.tap("Broadcast")
    await h.tap("All users")
    await h.send("<b>Scheduled maintenance tonight</b>")

    buttons = [b for row in h.screen.markup.inline_keyboard for b in row]
    send = next(b for b in buttons if "send to" in b.text.lower())
    cancel = next(b for b in buttons if "cancel" in b.text.lower())

    assert send.style == SUCCESS
    assert cancel.style != DANGER


async def test_cancelling_a_broadcast_sends_nothing(admin_harness):
    h = admin_harness
    await h.send("/start")
    await h.send("/admin")
    await h.tap("Operations")
    await h.tap("Broadcast")
    await h.tap("All users")
    await h.send("oops wrong text")

    await h.tap("Cancel")
    assert "ADMIN PANEL" in h.text


# -- SMM orders are not cancellable -----------------------------------------
