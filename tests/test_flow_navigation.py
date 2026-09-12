"""Top-level commands (/help, /balance, /orders, /cancel) and the catch-all
fallback for text sent outside any flow.

The core guarantee: arbitrary text is never mistaken for a deposit amount (or
any other typed input) unless the user is actually inside that flow's FSM
state. These commands must also work as an escape hatch *from inside* a flow.
"""


async def test_help_command_shows_the_help_center(harness):
    await harness.send("/help")
    assert "HELP CENTER" in harness.text


async def test_balance_command_shows_the_wallet(harness):
    await harness.send("/balance")
    assert "WALLET" in harness.text


async def test_orders_command_shows_orders_root(harness):
    await harness.send("/orders")
    assert "ORDERS" in harness.text.upper() or "orders" in harness.text.lower()


async def test_buy_command_shows_the_country_list(harness):
    await harness.send("/buy")
    assert "BUY NUMBER" in harness.text


async def test_account_command_shows_the_profile(harness):
    await harness.send("/account")
    assert "MY PROFILE" in harness.text


async def test_support_command_shows_the_help_center(harness):
    await harness.send("/support")
    assert "HELP CENTER" in harness.text


async def test_cancel_command_with_no_active_flow_is_harmless(harness):
    await harness.send("/cancel")
    assert harness.replied


async def test_cancel_escapes_the_deposit_amount_flow(harness):
    """/cancel must interrupt a flow instead of being parsed as its input."""
    await harness.send("/start")
    await harness.tap("Balance")
    await harness.tap("Add Balance")
    await harness.tap("fake_pay")
    assert "ENTER AMOUNT" in harness.text

    await harness.send("/cancel")

    assert "PAYMENT" not in harness.text
    # A follow-up plain number must not be treated as a leftover deposit amount.
    await harness.send("500")
    assert "PAYMENT" not in harness.text


async def test_arbitrary_text_outside_any_flow_is_not_treated_as_a_deposit_amount(harness):
    """Regression: typing a bare number with no flow active must not create an invoice."""
    await harness.send("/start")

    await harness.send("500")

    assert "PAYMENT" not in harness.text
    assert "₹500.00" not in harness.text


async def test_arbitrary_text_outside_any_flow_gets_a_helpful_reply(harness):
    await harness.send("/start")

    await harness.send("asdkjhaskjdh")

    assert harness.replied


async def test_catch_all_does_not_shadow_the_active_deposit_amount_state(harness):
    """The fallback must never fire while a real flow is waiting on input."""
    await harness.send("/start")
    await harness.tap("Balance")
    await harness.tap("Add Balance")
    await harness.tap("fake_pay")

    await harness.send("500")

    assert "PAYMENT" in harness.text
    assert "₹500.00" in harness.text
