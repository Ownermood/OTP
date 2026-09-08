"""The buy-a-number flow, end to end."""


from tests.flow_helpers import fund


async def test_buy_flow_end_to_end(harness, session_factory):
    """/start → Buy → country → service → confirm → a number on screen."""
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 10_000)

    await harness.tap("Buy Number")
    assert "BUY NUMBER" in harness.text
    # The country button carries the flag, dial code and cheapest price.
    assert any("🇮🇳" in b and "+91" in b and "11.00" in b for b in harness.buttons())

    await harness.tap("IN")
    assert "India" in harness.text
    assert any("WhatsApp" in b and "11.00" in b for b in harness.buttons())

    await harness.tap("WhatsApp")
    assert "ORDER CONFIRMATION" in harness.text
    assert "₹11.00" in harness.text

    await harness.tap("Confirm")
    assert "NUMBER PURCHASED" in harness.text
    assert "+91" in harness.text
    assert "Waiting for SMS" in harness.text


async def test_buying_debits_exactly_once(harness, session_factory):
    from app.services.wallet import WalletService

    await harness.send("/start")
    await fund(session_factory, harness.user_id, 10_000)

    await harness.tap("Buy Number")
    await harness.tap("IN")
    await harness.tap("WhatsApp")
    confirm = harness.screen.callback_for("Confirm")

    await harness.press(confirm)
    async with session_factory() as session:
        assert await WalletService(session).get_balance(harness.user_id) == 8_900


async def _reach_confirm(harness, session_factory, funds: int = 10_000) -> str:
    await harness.send("/start")
    await fund(session_factory, harness.user_id, funds)
    await harness.tap("Buy Number")
    await harness.tap("IN")
    await harness.tap("WhatsApp")
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
    await harness.tap("IN")
    await harness.tap("WhatsApp")
    await harness.tap("Confirm")

    assert "Insufficient balance" in harness.text
    assert "₹11.00" in harness.text  # what they needed
    assert harness.sms.created == 0


async def test_no_numbers_available_is_reported_and_refunded(harness, session_factory):
    from app.services.wallet import WalletService

    await harness.send("/start")
    await fund(session_factory, harness.user_id, 10_000)

    await harness.tap("Buy Number")
    await harness.tap("IN")
    await harness.tap("WhatsApp")
    harness.sms.fail_next = True
    await harness.tap("Confirm")

    assert "No numbers available" in harness.text
    async with session_factory() as session:
        assert await WalletService(session).get_balance(harness.user_id) == 10_000


async def test_country_search_comes_first(harness):
    """The opening screen searches countries, because it lists countries."""
    await harness.send("/start")
    await harness.tap("Buy Number")
    await harness.tap("Search")

    assert "SEARCH COUNTRY" in harness.text

    await harness.send("india")
    assert "Results for" in harness.text
    assert any("🇮🇳" in b for b in harness.buttons())


async def test_a_country_can_be_found_by_dial_code(harness):
    await harness.send("/start")
    await harness.tap("Buy Number")
    await harness.tap("Search")
    await harness.send("91")

    assert any("🇮🇳" in b for b in harness.buttons())


async def test_service_search_happens_inside_a_country(harness):
    await harness.send("/start")
    await harness.tap("Buy Number")
    await harness.tap("IN")
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


async def test_an_expired_quote_does_not_buy(harness, session_factory):
    """A token from a previous session must not resolve."""
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 10_000)

    await harness.tap("Buy Number")
    await harness.tap("IN")
    await harness.tap("WhatsApp")
    confirm = harness.screen.callback_for("Confirm")

    # Simulate the bot restarting between the quote and the tap.
    harness.dispatcher.workflow_data["tokens"] = type(
        harness.dispatcher.workflow_data["tokens"]
    )()

    await harness.press(confirm)
    assert harness.sms.created == 0
