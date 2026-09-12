"""Wallet: deposits, promo codes, transfers and history."""


from tests.flow_helpers import fund


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

    assert "minimum" in harness.text.lower()
    assert "50" in harness.text


async def test_deposit_of_exactly_the_minimum_is_accepted(harness):
    await harness.send("/start")
    await harness.tap("Balance")
    await harness.tap("Add Balance")
    await harness.tap("fake_pay")
    await harness.send("50")

    assert "PAYMENT" in harness.text
    assert "₹50.00" in harness.text


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


async def test_a_transfer_asks_before_moving_money(harness, session_factory, settings):
    """Regression: typing an amount used to send the money immediately."""
    from app.database.models import User
    from app.services.wallet import WalletService

    settings.transfer_enabled = True
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 50_000)

    async with session_factory() as session:
        session.add(User(id=606060, username="receiver", balance=0))
        await session.commit()

    await harness.send("/start")
    await harness.tap("Balance")
    await harness.tap("Transfer")
    await harness.send("@receiver")
    await harness.send("100")

    # Quoted, not sent.
    assert "CONFIRM TRANSFER" in harness.text
    assert "₹100.00" in harness.text
    async with session_factory() as session:
        assert await WalletService(session).get_balance(harness.user_id) == 50_000

    await harness.tap("Confirm")
    screens = [screen.text for screen in harness.session.screens]
    assert any("TRANSFER SENT" in text for text in screens)
    # The recipient is told as well.
    assert any("BALANCE RECEIVED" in text for text in screens)
    async with session_factory() as session:
        wallet = WalletService(session)
        assert await wallet.get_balance(harness.user_id) == 40_000
        assert await wallet.get_balance(606060) == 10_000


async def test_a_confirmed_transfer_cannot_be_sent_twice(harness, session_factory, settings):
    from app.database.models import User
    from app.services.wallet import WalletService

    settings.transfer_enabled = True
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 50_000)
    async with session_factory() as session:
        session.add(User(id=606061, username="receiver2", balance=0))
        await session.commit()

    await harness.send("/start")
    await harness.tap("Balance")
    await harness.tap("Transfer")
    await harness.send("@receiver2")
    await harness.send("100")
    confirm = harness.screen.callback_for("Confirm")

    await harness.press(confirm)
    harness.forget_last_tap()
    await harness.press(confirm)

    async with session_factory() as session:
        assert await WalletService(session).get_balance(harness.user_id) == 40_000
