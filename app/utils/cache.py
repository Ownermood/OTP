"""A tiny in-process TTL cache.

Only *static* provider metadata belongs here -- service catalogues, country
lists, SMM service lists. Balances, payment states and order states are never
cached; they are always read from the database or the provider.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Single-value cache with a refresh coroutine and a time-to-live."""

    def __init__(self, loader: Callable[[], Awaitable[T]], ttl: int) -> None:
        self._loader = loader
        self._ttl = ttl
        self._value: T | None = None
        self._loaded_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self, force_refresh: bool = False) -> T:
        """Return the cached value, refreshing it when stale."""
        if not force_refresh and self._value is not None and not self._is_stale:
            return self._value
        async with self._lock:
            # Another coroutine may have refreshed while we waited for the lock.
            if force_refresh or self._value is None or self._is_stale:
                self._value = await self._loader()
                self._loaded_at = time.monotonic()
        return self._value  # type: ignore[return-value]

    def invalidate(self) -> None:
        self._value = None

    @property
    def _is_stale(self) -> bool:
        return time.monotonic() - self._loaded_at > self._ttl
