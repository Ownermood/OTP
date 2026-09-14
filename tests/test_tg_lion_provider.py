"""The TG-Lion adapter against recorded/plausible provider responses.

Shapes are taken directly from reference/OTPBotPanel/otpbotpannel-main/
(tg_lion.py + plugins/numbers.py) -- the only real evidence available for
what TG-Lion actually answers, since this deployment has no live TG-Lion
credentials configured.
"""

from decimal import Decimal

import httpx
import pytest

from app.core.exceptions import ProviderAuthError, ProviderError
from app.providers.tg_lion import TgLionProvider

COUNTRIES = {
    "countries": {
        "in": {"name": "India", "price": "10", "stock": 50},
        "us": {"name": "USA", "price": "25"},
    }
}


class FakeApi:
    """A stand-in for TG-Lion.net that records what it was asked."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.number_status = "ok"
        self.code: str | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        self.calls.append(params)
        action = params.get("action", "")

        if action == "available_countries":
            return httpx.Response(200, json={"status": "ok", **COUNTRIES})
        if action == "country_info":
            code = params.get("country_code")
            info = COUNTRIES["countries"].get(code, {})
            return httpx.Response(200, json={"status": "ok", **info})
        if action == "getNumber":
            if self.number_status != "ok":
                return httpx.Response(200, json={"status": "fail", "message": "no stock"})
            return httpx.Response(200, json={"status": "ok", "Number": "+19290001234"})
        if action == "getCode":
            if self.code is None:
                return httpx.Response(200, json={"status": "ok"})  # no code yet
            return httpx.Response(200, json={"status": "ok", "code": self.code, "pass": "None"})
        if action == "get_balance":
            return httpx.Response(200, json={"status": "ok", "balance": "5.50"})
        return httpx.Response(200, json={"status": "fail", "message": "unknown action"})

    def actions(self) -> list[str]:
        return [call.get("action", "") for call in self.calls]


def build(api: FakeApi, rate: str = "80") -> TgLionProvider:
    provider = TgLionProvider(
        api_key="k", your_id="id", base_url="https://TG-Lion.net", currency_rate=Decimal(rate)
    )
    provider._client = httpx.AsyncClient(
        base_url="https://TG-Lion.net", transport=httpx.MockTransport(api.handler)
    )
    return provider


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()


async def test_every_call_carries_the_configured_credentials(api):
    provider = build(api)
    await provider.get_countries()
    assert all(call.get("apiKey") == "k" and call.get("YourID") == "id" for call in api.calls)
    await provider.close()


async def test_countries_are_parsed_and_priced_in_our_currency(api):
    provider = build(api)
    countries = await provider.get_countries()
    india = next(c for c in countries if c.code == "in")
    assert india.name == "India"
    assert india.cost == 80_000  # 10 * rate 80 = 800 major units = 80000 minor units
    assert india.available == 50
    await provider.close()


async def test_a_country_with_no_stock_field_still_parses(api):
    provider = build(api)
    countries = await provider.get_countries()
    usa = next(c for c in countries if c.code == "us")
    assert usa.available is None
    await provider.close()


async def test_buying_a_number_parses_the_reply(api):
    provider = build(api)
    number = await provider.create_number("in")
    assert number.number == "+19290001234"
    assert api.actions() == ["getNumber"]
    await provider.close()


async def test_a_purchase_never_retries(api):
    """retries=0 for getNumber: a retried purchase could double-buy."""
    provider = build(api)
    api.number_status = "fail"
    with pytest.raises(ProviderError):
        await provider.create_number("in")
    assert api.actions().count("getNumber") == 1
    await provider.close()


async def test_no_stock_is_a_provider_error_not_a_crash(api):
    provider = build(api)
    api.number_status = "fail"
    with pytest.raises(ProviderError):
        await provider.create_number("in")
    await provider.close()


async def test_no_code_yet_is_none_not_an_error(api):
    """Waiting for a code must never look like a provider failure."""
    provider = build(api)
    result = await provider.get_code("+19290001234")
    assert result is None
    await provider.close()


async def test_a_received_code_is_parsed(api):
    provider = build(api)
    api.code = "654321"
    result = await provider.get_code("+19290001234")
    assert result is not None
    assert result.code == "654321"
    await provider.close()


async def test_refresh_never_calls_getnumber_again(api):
    """The single most important safety property of Refresh/Get OTP."""
    provider = build(api)
    await provider.get_code("+19290001234")
    await provider.get_code("+19290001234")
    await provider.get_code("+19290001234")
    assert "getNumber" not in api.actions()
    await provider.close()


async def test_the_balance_check_works(api):
    provider = build(api)
    assert await provider.get_balance() == 44_000  # 5.50 * 80 = 440 major = 44000 minor
    await provider.close()


async def test_a_bad_credentials_message_is_mapped_to_an_auth_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "fail", "message": "invalid api key"})

    provider = TgLionProvider(
        api_key="bad", your_id="id", base_url="https://TG-Lion.net", currency_rate=Decimal(80)
    )
    provider._client = httpx.AsyncClient(
        base_url="https://TG-Lion.net", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ProviderAuthError):
        await provider.get_countries()
    await provider.close()


async def test_a_non_json_body_is_a_provider_error_not_a_crash():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    provider = TgLionProvider(
        api_key="k", your_id="id", base_url="https://TG-Lion.net", currency_rate=Decimal(80)
    )
    provider._client = httpx.AsyncClient(
        base_url="https://TG-Lion.net", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ProviderError):
        await provider.get_countries()
    await provider.close()


async def test_missing_countries_key_is_a_provider_error_not_a_crash():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    provider = TgLionProvider(
        api_key="k", your_id="id", base_url="https://TG-Lion.net", currency_rate=Decimal(80)
    )
    provider._client = httpx.AsyncClient(
        base_url="https://TG-Lion.net", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ProviderError):
        await provider.get_countries()
    await provider.close()
