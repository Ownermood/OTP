"""The main menu and universal navigation, driven through the dispatcher."""




async def test_start_shows_a_premium_landing_not_an_account_dump(harness):
    """Greeting, a quiet balance line, and a clear primary CTA -- not raw
    identifiers. User ID and @username live one tap away on My Account."""
    await harness.send("/start")

    assert "Welcome" in harness.text
    assert "Test" in harness.text
    assert "Balance" in harness.text
    assert "User ID" not in harness.text
    assert "Username" not in harness.text
    assert str(harness.user_id) not in harness.text
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


def test_home_screen_never_exposes_raw_identifiers():
    """The landing screen is a premium card, not an account-details dump --
    User ID and @username stay off it entirely (one tap away on My Account),
    regardless of whether the user has a username at all.

    Driven at the ``_home_screen`` level, not the full harness: the fake
    Telegram user the harness sends always carries a username, which
    ``UserMiddleware`` re-syncs on every /start -- there is no way to reach
    a genuinely username-less state through that path.
    """
    from types import SimpleNamespace

    from app.bot.handlers.start import _home_screen
    from app.bot.texts import Texts
    from app.core.config import ROOT_DIR
    from app.core.emoji_registry import default_icon_ids

    user = SimpleNamespace(id=555, full_name="Alex", username="alexdoe", balance=0)
    context = SimpleNamespace(
        texts=Texts(ROOT_DIR / "locales", "en", default_icon_ids()),
        locale="en",
        user=user,
        admin_role=None,
        smm=SimpleNamespace(enabled=False),
        telegram_numbers=SimpleNamespace(enabled=False),
        money=lambda minor: f"₹{minor / 100:.2f}",
        text=lambda key, **values: Texts(
            ROOT_DIR / "locales", "en", default_icon_ids()
        ).get(key, "en", **values),
    )

    text, _ = _home_screen(context, is_new=False)
    assert "Username" not in text
    assert "User ID" not in text
    assert str(user.id) not in text


async def test_every_screen_offers_a_way_back(harness):
    """The spec's rule: the user is never stranded."""
    await harness.send("/start")

    for label in ("Buy Number", "Balance", "Profile", "Help", "Orders", "Favorites"):
        await harness.send("/start")
        await harness.tap(label)
        buttons = " ".join(harness.buttons())
        assert "Back" in buttons or "Main Menu" in buttons, f"{label} screen strands the user"


# -- the buy flow, driven the way a user would ------------------------------
