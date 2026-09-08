"""The worker loop itself, plus the timing constants every worker shares."""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger

logger = get_logger(__name__)

#: When nothing is in flight, sleep this long instead of the tight interval.
IDLE_INTERVAL = 30

#: How long an order may sit without a provider id before it is treated as
#: orphaned. Comfortably longer than a provider call, so a purchase in flight
#: is never swept out from under itself.
ORPHAN_GRACE_SECONDS = 180

class BaseWorker:
    """A cancellable loop with crash isolation per tick."""

    name = "worker"

    def __init__(self, interval: int) -> None:
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop(), name=self.name)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            delay = self._interval
            try:
                delay = await self.tick() or self._interval
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # One bad tick must never end the loop.
                logger.error("worker.tick_failed", worker=self.name, error=str(exc), exc_info=True)
            await asyncio.sleep(delay)

    async def tick(self) -> int | None:
        """Run one iteration. Return a sleep override, or ``None`` for the default."""
        raise NotImplementedError
