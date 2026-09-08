"""A slow screen must not become a crash when Telegram gives up on the query."""

from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery

from app.bot.ack import acknowledge
from app.services.workers.catalogue import CatalogueWorker
from tests.fakes import FakeSmsProvider
from tests.test_temporasms import FakeApi, build


def expired(message: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=AnswerCallbackQuery(callback_query_id="1"), message=message)


class FakeQuery:
    def __init__(self, error: Exception | None = None) -> None:
        self.data = "buy_services"
        self.answer = AsyncMock(side_effect=error)


@pytest.mark.parametrize(
    "message",
    [
        "Bad Request: query is too old and response timeout expired or query ID is invalid",
        "Bad Request: query ID is invalid",
    ],
)
async def test_an_expired_query_is_swallowed(message):
    await acknowledge(FakeQuery(expired(message)))  # must not raise


async def test_a_real_failure_still_surfaces():
    with pytest.raises(TelegramBadRequest):
        await acknowledge(FakeQuery(expired("Bad Request: message text is empty")))


async def test_the_answer_carries_the_toast_text():
    query = FakeQuery()
    await acknowledge(query, "Saved", alert=True)
    query.answer.assert_awaited_once_with("Saved", show_alert=True)


async def test_the_worker_builds_the_catalogue_before_any_request_does():
    api = FakeApi(bulk_prices=True)
    provider = build(api)
    worker = CatalogueWorker(provider)

    assert await worker.tick() is None
    fetches = api.actions().count("getPrices")

    # The screen a user opens next reuses that work rather than repeating it.
    await provider.get_services()
    assert api.actions().count("getPrices") == fetches
    await provider.close()


async def test_a_provider_with_nothing_cached_warms_to_nothing():
    """Warming is optional: a provider that answers directly has no cache."""
    assert await FakeSmsProvider().warm() is None
