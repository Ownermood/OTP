"""Error handling and access control."""


from tests.flow_helpers import fund


async def test_a_crashing_provider_shows_a_friendly_message_not_a_traceback(
    harness, session_factory, monkeypatch
):
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 10_000)

    async def explode(*args, **kwargs):
        raise RuntimeError("upstream exploded")

    await harness.tap("Buy Number")
    # Patched after the country list is cached, so the crash lands on the
    # per-country service lookup, which is resolved on the next tap.
    monkeypatch.setattr(harness.sms, "get_services_for", explode)
    await harness.tap("IN")

    assert "Something went wrong" in harness.text
    assert "Traceback" not in harness.text
    assert "RuntimeError" not in harness.text


async def test_a_banned_user_is_turned_away(harness, session_factory):
    from app.database.repositories import UserRepository

    await harness.send("/start")
    async with session_factory() as session:
        await UserRepository(session).set_banned(harness.user_id, True, "abuse")
        await session.commit()

    await harness.send("/start")
    assert "suspended" in harness.text


async def test_one_user_cannot_open_another_users_order(harness, session_factory):
    """An order id lifted from someone else's callback must not resolve."""
    from app.core.constants import OrderKind, OrderStatus
    from app.database.repositories import OrderRepository, UserRepository

    await harness.send("/start")
    async with session_factory() as session:
        await UserRepository(session).get_or_create(999888, "victim", "Victim")
        order = await OrderRepository(session).create(
            user_id=999888,
            kind=OrderKind.ACTIVATION,
            status=OrderStatus.PROCESSING,
            provider="fake_sms",
            service_code="wa",
            service_name="WhatsApp",
            country_id=22,
            country_name="India",
            price=1_100,
            phone="+919999999999",
        )
        await session.commit()
        stolen_id = order.id

    from app.bot.callbacks import OrderCB

    await harness.press(OrderCB(action="detail", order_id=stolen_id).pack())

    assert "Order not found" in harness.text
    assert "+919999999999" not in harness.text
