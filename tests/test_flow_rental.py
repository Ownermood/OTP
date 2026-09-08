"""The rent-a-number flow."""


from tests.flow_helpers import fund


async def test_rental_flow_end_to_end(harness, session_factory):
    """Country → duration → services at real prices → confirm."""
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 100_000)

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
    await fund(session_factory, harness.user_id, 500_000)

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
    await fund(session_factory, harness.user_id, 500_000)

    await harness.tap("Rent Number")
    await harness.tap("India")
    await harness.tap("Custom")
    assert "CUSTOM DURATION" in harness.text

    await harness.send("99999")  # above MAX_RENTAL_HOURS
    assert "does not look right" in harness.text.lower()


# -- error handling and access control --------------------------------------
