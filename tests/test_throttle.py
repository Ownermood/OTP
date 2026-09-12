"""ThrottleMiddleware's per-user dedup/rate-limit state must not grow forever.

Every distinct user who has ever sent an update leaves one entry in
``_last_seen`` and (for callbacks) ``_last_callback``. With no eviction, a
long-running process accumulates one entry per distinct user for as long as
it runs -- unbounded memory growth with no relationship to current traffic.
"""

from unittest.mock import AsyncMock

from aiogram.types import User as TgUser

from app.bot.middlewares import ThrottleMiddleware


async def test_stale_per_user_throttle_state_is_evicted(monkeypatch):
    middleware = ThrottleMiddleware(rate_per_second=1000)
    handler = AsyncMock(return_value="ok")

    fake_now = [1_000.0]
    monkeypatch.setattr("app.bot.middlewares.time.monotonic", lambda: fake_now[0])

    for uid in range(50):
        user = TgUser(id=uid, is_bot=False, first_name="U")
        await middleware(handler, object(), {"event_from_user": user})

    assert len(middleware._last_seen) == 50

    # Long past any window that could still affect a throttling decision.
    fake_now[0] += 3600.0
    late_user = TgUser(id=99_999, is_bot=False, first_name="U")
    await middleware(handler, object(), {"event_from_user": late_user})

    assert len(middleware._last_seen) == 1
    assert 99_999 in middleware._last_seen
