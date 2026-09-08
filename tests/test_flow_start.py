"""The main menu and universal navigation, driven through the dispatcher."""




async def test_start_shows_the_welcome_and_the_main_menu(harness):
    await harness.send("/start")

    assert "WELCOME" in harness.text
    # Labels carry colour cues and casing that may be tuned; assert on the
    # words, not the decoration.
    buttons = " ".join(harness.buttons()).lower()
    assert "buy number" in buttons
    assert "balance" in buttons
    assert "help" in buttons


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
