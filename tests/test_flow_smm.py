"""The SMM panel flow."""


from tests.flow_helpers import fund


async def test_smm_order_flow_end_to_end(harness, session_factory):
    """Platform → service → link → quantity → confirm → order created."""
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 200_000)

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
    await fund(session_factory, harness.user_id, 200_000)
    await harness.tap("SMM Panel")
    await harness.tap("Instagram")
    await harness.tap("Instagram Followers")

    await harness.send("not-a-link")
    assert "does not look right" in harness.text.lower()


async def test_smm_enforces_quantity_bounds(harness, session_factory):
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 200_000)
    await harness.tap("SMM Panel")
    await harness.tap("Instagram")
    await harness.tap("Instagram Followers")
    await harness.send("https://instagram.com/example")

    await harness.send("5")  # below the service minimum of 100
    assert "does not look right" in harness.text.lower()


async def test_smm_order_can_be_tracked(harness, session_factory):
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 200_000)
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
