"""The TG-Lion Telegram-number flow, end to end through the real bot."""

from tests.flow_helpers import fund


async def test_telegram_numbers_flow_end_to_end(harness, session_factory):
    """Home -> Telegram Numbers -> country -> buy -> Get OTP -> waiting -> code."""
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 200_000)

    assert any("Telegram Numbers" in b for b in harness.buttons())
    await harness.tap("Telegram Numbers")
    assert "TELEGRAM NUMBERS" in harness.text
    assert any("India" in b for b in harness.buttons())

    await harness.tap("India")
    assert "India" in harness.text
    assert "Price" in harness.text

    await harness.tap("Buy Now")
    assert "NUMBER PURCHASED" in harness.text
    assert harness.tg_lion.created == 1

    await harness.tap("Get OTP")
    assert "WAITING FOR YOUR CODE" in harness.text
    assert any("refresh" in b.lower() for b in harness.buttons())

    from app.providers.tg_lion import TgLionCode

    harness.tg_lion.next_code = TgLionCode(code="778899")
    harness.forget_last_tap()  # Get OTP and Refresh share one callback_data
    await harness.tap("Refresh")
    assert "CODE RECEIVED" in harness.text
    assert "778899" in harness.text

    buttons = [b for row in harness.screen.markup.inline_keyboard for b in row]
    copy_texts = {b.copy_text.text for b in buttons if b.copy_text is not None}
    assert "778899" in copy_texts
    assert any(t.startswith("+1929") for t in copy_texts)
    assert any("buy again" in b.text.lower() for b in buttons)


async def test_country_search_finds_by_name_iso_code_and_dial_code(harness):
    await harness.send("/start")
    await harness.tap("Telegram Numbers")
    await harness.tap("Search")
    assert "SEARCH COUNTRY" in harness.text

    await harness.send("united states")
    assert "Results for" in harness.text
    assert any("United States" in b for b in harness.buttons())

    await harness.send("/start")
    await harness.tap("Telegram Numbers")
    await harness.tap("Search")
    await harness.send("us")
    assert any("United States" in b for b in harness.buttons())
    assert not any("India" in b for b in harness.buttons())

    await harness.send("/start")
    await harness.tap("Telegram Numbers")
    await harness.tap("Search")
    await harness.send("91")
    assert any("India" in b for b in harness.buttons())


async def test_country_search_with_no_matches_offers_a_way_back(harness):
    await harness.send("/start")
    await harness.tap("Telegram Numbers")
    await harness.tap("Search")
    await harness.send("zzzzz")

    assert "No matches" in harness.text
    assert any("main menu" in b.lower() for b in harness.buttons())


async def test_refreshing_never_buys_a_second_number(harness, session_factory):
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 200_000)
    await harness.tap("Telegram Numbers")
    await harness.tap("India")
    await harness.tap("Buy Now")

    await harness.tap("Get OTP")
    harness.forget_last_tap()
    await harness.tap("Refresh")
    harness.forget_last_tap()
    await harness.tap("Refresh")

    assert harness.tg_lion.created == 1


async def test_a_second_purchase_is_refused_while_one_is_open(harness, session_factory):
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 200_000)
    await harness.tap("Telegram Numbers")
    await harness.tap("India")
    await harness.tap("Buy Now")

    await harness.send("/start")
    await harness.tap("Telegram Numbers")
    await harness.tap("India")
    await harness.tap("Buy Now")

    assert any("already" in a.lower() for a in harness.alerts) or "already" in harness.text.lower()
    assert harness.tg_lion.created == 1


async def test_cancelling_refunds_and_credits_nothing_twice(harness, session_factory):
    from app.services.wallet import WalletService

    await harness.send("/start")
    await fund(session_factory, harness.user_id, 200_000)
    await harness.tap("Telegram Numbers")
    await harness.tap("India")
    await harness.tap("Buy Now")

    await harness.tap("Cancel")
    assert "CANCELLED" in harness.text

    async with session_factory() as session:
        assert await WalletService(session).get_balance(harness.user_id) == 200_000


async def test_telegram_order_reachable_and_refreshable_from_my_orders(harness, session_factory):
    """The generic My Orders list (not the dedicated tg_lion screens) must
    also route a TELEGRAM order's refresh/detail correctly."""
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 200_000)
    await harness.tap("Telegram Numbers")
    await harness.tap("India")
    await harness.tap("Buy Now")

    await harness.send("/orders")
    await harness.tap("Telegram Numbers")
    assert "TELEGRAM NUMBERS" in harness.text
    assert any("Telegram Number" in b for b in harness.buttons())

    await harness.tap("#1")
    assert "Telegram Number" in harness.text or "India" in harness.text

    from app.providers.tg_lion import TgLionCode

    harness.tg_lion.next_code = TgLionCode(code="445566")
    await harness.tap("Refresh")
    assert "445566" in harness.text


async def test_disabled_module_hides_the_button_and_refuses_the_flow(harness, session_factory):
    """When TG-Lion has no provider configured, the button must not appear,
    and the flow must fail cleanly rather than crash if reached anyway."""
    harness.dispatcher.workflow_data["tg_lion_provider"] = None

    await harness.send("/start")
    assert not any("Telegram Numbers" in b for b in harness.buttons())

    from app.bot.callbacks import Nav

    await harness.press(Nav(to="telegram").pack())
    assert "unavailable" in harness.text.lower()


async def test_country_selection_buttons_in_the_existing_buy_flow_are_unaffected(
    harness, session_factory
):
    """Explicit requirement: nothing about the existing SMS-activation Buy
    flow (a completely different provider) changes because TG-Lion exists."""
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 10_000)
    await harness.tap("Buy Number")

    buttons = [b for row in harness.screen.markup.inline_keyboard for b in row]
    country_buttons = [b for b in buttons if "🇮🇳" in b.text or "+91" in b.text]
    assert country_buttons
    for b in country_buttons:
        assert b.style is None
        assert b.icon_custom_emoji_id is None
