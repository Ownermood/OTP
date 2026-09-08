"""The TemporaSMS adapter against recorded provider responses.

Every payload below is the shape the live API actually answered with, so
these tests fail if the adapter drifts back to SMS-Activate's assumptions.
"""

from decimal import Decimal

import httpx
import pytest

from app.core.exceptions import NoNumbersAvailableError
from app.providers.service_names import service_name
from app.providers.temporasms import TemporaSmsProvider

OPERATORS = {"OPERATOR 1": "1", "OPERATOR 2": "2"}
COUNTRIES = {
    "22": {"id": 22, "rus": "Индия", "eng": "india"},
    "6": {"id": 6, "rus": "Индонезия", "eng": "indonesia"},
}
# One service, three price tiers, the cheapest of which is out of stock.
PRICES_22 = {"22": {"ttf": {"0.0195": 0, "0.0400": 118, "1.3024": 5}, "obi": {"0.5000": 3}}}
PRICES_6 = {"6": {"ttf": {"0.0600": 40}}}


class FakeApi:
    """A stand-in for handler_api.php that records what it was asked."""

    def __init__(self, *, bulk_prices: bool = False, missing: set[str] = frozenset()) -> None:
        self.bulk_prices = bulk_prices
        self.missing = set(missing)
        self.calls: list[dict[str, str]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        self.calls.append(params)
        action = params.get("action", "")
        if action in self.missing:
            return httpx.Response(200, text="BAD_ACTION")
        if action != "getOperators" and "operator" not in params:
            return httpx.Response(200, text="BAD_OPERATOR")
        if action == "getOperators":
            return httpx.Response(200, json=OPERATORS)
        if action == "getCountries":
            return httpx.Response(200, json=COUNTRIES)
        if action == "getPrices":
            country = params.get("country")
            if country is None:
                if not self.bulk_prices:
                    return httpx.Response(200, text="BAD_COUNTRY")
                return httpx.Response(200, json={**PRICES_22, **PRICES_6})
            return httpx.Response(200, json=PRICES_22 if country == "22" else PRICES_6)
        if action == "getNumber":
            return httpx.Response(200, text="ACCESS_NUMBER:987654:919876543210")
        return httpx.Response(200, text="BAD_ACTION")

    def actions(self) -> list[str]:
        return [call.get("action", "") for call in self.calls]


def build(api: FakeApi, rate: str = "100") -> TemporaSmsProvider:
    provider = TemporaSmsProvider(
        api_key="k",
        base_url="https://api.temporasms.com/",
        currency_rate=Decimal(rate),
    )
    provider._client = httpx.AsyncClient(
        base_url="https://api.temporasms.com/",
        params={"api_key": "k"},
        transport=httpx.MockTransport(api.handler),
    )
    return provider


@pytest.fixture
def api() -> FakeApi:
    return FakeApi(bulk_prices=True)


async def test_every_catalogue_call_carries_an_operator(api):
    provider = build(api)
    await provider.get_services()
    catalogue_calls = [c for c in api.calls if c["action"] != "getOperators"]
    assert catalogue_calls
    assert all("operator" in call for call in catalogue_calls)
    assert not any("BAD_OPERATOR" in call.get("action", "") for call in api.calls)
    await provider.close()


async def test_the_cheapest_in_stock_tier_is_quoted(api):
    provider = build(api)
    # 0.0195 has no stock, so the quote is 0.0400 * 100 = 4.00 = 400 paise.
    assert await provider.get_price("ttf", 22) == 400
    await provider.close()


async def test_stock_sums_across_the_tiers_that_have_any(api):
    provider = build(api)
    countries = await provider.get_countries("ttf")
    india = next(country for country in countries if country.id == 22)
    assert india.available == 123  # 118 + 5, the empty tier contributing nothing
    assert india.name == "India"
    await provider.close()


async def test_countries_are_ordered_cheapest_first(api):
    provider = build(api)
    countries = await provider.get_countries("ttf")
    assert [country.id for country in countries] == [22, 6]
    await provider.close()


async def test_a_service_offered_nowhere_has_no_price(api):
    provider = build(api)
    with pytest.raises(NoNumbersAvailableError):
        await provider.get_price("nope", 22)
    await provider.close()


async def test_service_codes_get_names_when_we_know_them(api):
    provider = build(api)
    services = await provider.get_services()
    codes = {service.code: service.name for service in services}
    assert codes["ttf"] == "TTF"  # unknown code shown as-is rather than guessed
    await provider.close()


def test_known_codes_resolve_to_product_names():
    assert service_name("wa") == "WhatsApp"
    assert service_name("TG") == "Telegram"
    assert service_name("zzz") == "ZZZ"


async def test_the_catalogue_is_fetched_once_and_reused(api):
    provider = build(api)
    await provider.get_services()
    await provider.get_countries("ttf")
    await provider.get_price("ttf", 22)
    assert api.actions().count("getPrices") == 1
    await provider.close()


async def test_a_provider_without_bulk_prices_is_walked_country_by_country():
    api = FakeApi(bulk_prices=False)
    provider = build(api)
    countries = await provider.get_countries("ttf")
    assert {country.id for country in countries} == {22, 6}
    # One rejected bulk attempt, then one call per country.
    assert api.actions().count("getPrices") == 3
    await provider.close()


async def test_the_endpoints_this_provider_lacks_are_never_needed():
    api = FakeApi(bulk_prices=True, missing={"getServicesList", "getTopCountriesByService"})
    provider = build(api)
    assert await provider.get_services()
    assert await provider.get_countries("ttf")
    await provider.close()


async def test_buying_a_number_sends_the_operator_and_parses_the_reply(api):
    provider = build(api)
    activation = await provider.create_activation("ttf", 22)
    assert activation.provider_order_id == "987654"
    assert activation.phone == "919876543210"
    assert activation.cost == 400
    get_number = next(call for call in api.calls if call["action"] == "getNumber")
    assert get_number["operator"] == "1"
    await provider.close()


async def test_a_failed_refresh_keeps_serving_the_last_good_catalogue(api):
    provider = build(api)
    await provider.get_services()
    provider._fetched_at = 0.0  # force the TTL to have expired
    api.missing = {"getPrices", "getCountries"}
    assert await provider.get_countries("ttf")
    await provider.close()
