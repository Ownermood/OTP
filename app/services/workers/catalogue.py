"""Keeps the SMS provider's catalogue warm.

Some providers assemble their catalogue from calls that take tens of seconds.
Doing that inside a button press cost one user a 22-second wait and then the
crash that follows it: Telegram expires a callback query long before the
answer arrives. Refreshing on a loop moves that cost off every request path,
so the cache is already populated when a screen needs it.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.providers.base import BaseSMSProvider
from app.services.workers.base import BaseWorker

logger = get_logger(__name__)

#: Shorter than any provider's own cache lifetime, so it never goes cold and
#: a user is never the one who pays to rebuild it.
REFRESH_INTERVAL = 240


class CatalogueWorker(BaseWorker):
    """Rebuilds the provider's cached catalogue before it expires."""

    name = "catalogue_worker"

    def __init__(self, sms_provider: BaseSMSProvider, interval: int = REFRESH_INTERVAL) -> None:
        super().__init__(interval)
        self._provider = sms_provider

    async def tick(self) -> int | None:
        services = await self._provider.warm()
        if services is not None:
            logger.info("catalogue.warmed", provider=self._provider.name, services=services)
        return None
