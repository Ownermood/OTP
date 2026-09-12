"""Shutdown drains in-flight handlers.

aiogram cancels its polling task on SIGTERM but leaves the handler tasks it
spawned running, and the loop closes under them. A deploy landing mid-purchase
would abandon a handler between the wallet debit and the provider call. These
tests are about that handler being allowed to finish.
"""

import asyncio

import pytest


@pytest.fixture
def dispatcher(harness):
    return harness.dispatcher


async def test_an_in_flight_handler_is_allowed_to_finish(dispatcher, harness):
    finished: list[str] = []

    async def slow_handler() -> None:
        await asyncio.sleep(0.05)
        finished.append("done")

    task = asyncio.create_task(slow_handler())
    dispatcher._handle_update_tasks.add(task)

    await dispatcher.emit_shutdown()

    assert finished == ["done"], "the handler was abandoned mid-flight"
    assert task.done() and not task.cancelled()


async def test_several_handlers_all_finish(dispatcher):
    finished: list[int] = []

    async def handler(index: int) -> None:
        await asyncio.sleep(0.01 * index)
        finished.append(index)

    for index in range(1, 5):
        dispatcher._handle_update_tasks.add(asyncio.create_task(handler(index)))

    await dispatcher.emit_shutdown()

    assert sorted(finished) == [1, 2, 3, 4]


async def test_a_stuck_handler_does_not_hold_the_deploy_forever(
    dispatcher, harness, settings
):
    """A handler blocked on a dead provider must not stall the shutdown."""
    settings.shutdown_drain_seconds = 0.05

    async def stuck() -> None:
        await asyncio.sleep(30)

    task = asyncio.create_task(stuck())
    dispatcher._handle_update_tasks.add(task)

    await asyncio.wait_for(dispatcher.emit_shutdown(), timeout=2)

    assert task.cancelled() or task.done()


async def test_shutdown_is_quick_when_nothing_is_running(dispatcher):
    loop = asyncio.get_running_loop()
    started = loop.time()

    await dispatcher.emit_shutdown()

    assert loop.time() - started < 0.5


async def test_a_completed_handler_is_not_waited_on(dispatcher):
    async def already_done() -> None:
        return None

    task = asyncio.create_task(already_done())
    await task
    dispatcher._handle_update_tasks.add(task)

    await asyncio.wait_for(dispatcher.emit_shutdown(), timeout=1)


async def test_a_cancelled_handler_still_runs_its_async_rollback(
    dispatcher, harness, settings
):
    """Cancelling a stuck handler must not skip its rollback/cleanup code.

    Calling ``task.cancel()`` only *schedules* the cancellation; the task must
    still be awaited for the ``CancelledError`` to be delivered and for an
    async ``finally`` (e.g. ``await session.rollback()``) to actually finish
    running. If ``drain()`` returns without awaiting the cancelled tasks, the
    process can go on to dispose the engine while a rollback is still
    in-flight.
    """
    settings.shutdown_drain_seconds = 0.05
    cleaned_up: list[str] = []

    async def stuck_with_async_cleanup() -> None:
        try:
            await asyncio.sleep(30)
        finally:
            # Multiple await hops, like a real `session.rollback()` would take.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            cleaned_up.append("rolled back")

    task = asyncio.create_task(stuck_with_async_cleanup())
    dispatcher._handle_update_tasks.add(task)

    await asyncio.wait_for(dispatcher.emit_shutdown(), timeout=2)

    assert cleaned_up == ["rolled back"], "async rollback did not complete before shutdown returned"


async def test_a_renamed_aiogram_attribute_does_not_break_shutdown(dispatcher, monkeypatch):
    """The drain reaches into a private attribute; an upgrade must not crash."""
    monkeypatch.delattr(type(dispatcher), "_handle_update_tasks", raising=False)
    monkeypatch.setattr(dispatcher, "_handle_update_tasks", None, raising=False)

    await asyncio.wait_for(dispatcher.emit_shutdown(), timeout=1)
