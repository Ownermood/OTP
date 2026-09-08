"""Order history, detail, favourites, referrals, profile and help."""


from tests.flow_helpers import fund


async def test_orders_screen_lists_a_purchase(harness, session_factory):
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 10_000)
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
    await fund(session_factory, harness.user_id, 10_000)
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
    await fund(session_factory, harness.user_id, 10_000)

    await harness.send("/start")
    await harness.tap("Profile")

    assert "MY PROFILE" in harness.text
    assert "₹100.00" in harness.text
    assert "Numbers purchased" in harness.text


async def test_favorites_can_be_added_from_a_quote_and_bought_back(harness, session_factory):
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 10_000)

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


async def test_an_smm_order_offers_no_cancel_button(harness, session_factory):
    """It is already being delivered; refunding it would be a straight loss."""
    h = harness
    await h.send("/start")
    await fund(session_factory, h.user_id, 200_000)
    await h.tap("SMM Panel")
    await h.tap("Instagram")
    await h.tap("Instagram Followers")
    await h.send("https://instagram.com/example")
    await h.send("500")
    await h.tap("Confirm")

    await h.send("/start")
    await h.tap("Orders")
    await h.tap("SMM")
    await h.tap("#1")

    buttons = " ".join(h.buttons())
    assert "Refresh" in buttons
    assert "Cancel" not in buttons


async def test_an_activation_still_offers_cancel(harness, session_factory):
    h = harness
    await h.send("/start")
    await fund(session_factory, h.user_id, 10_000)
    await h.tap("Buy Number")
    await h.tap("WhatsApp")
    await h.tap("India")
    await h.tap("Confirm")

    await h.send("/start")
    await h.tap("Orders")
    await h.tap("SMS Activations")
    await h.tap("#1")

    assert "Cancel" in " ".join(h.buttons())
