"""Show All: the whole catalogue as text, not as pages of buttons."""

import pytest

from tests.flow_helpers import fund


async def test_the_services_screen_offers_show_all_and_search(harness):
    await harness.send("/start")
    await harness.tap("Buy Number")

    buttons = " ".join(harness.buttons())
    assert "Show All" in buttons
    assert "Search" in buttons


async def test_show_all_services_lists_them(harness):
    await harness.send("/start")
    await harness.tap("Buy Number")
    await harness.tap("Show All")

    assert "ALL SERVICES" in harness.text
    assert "WhatsApp" in harness.text
    assert "<code>wa</code>" in harness.text


async def test_the_countries_screen_offers_show_all(harness):
    await harness.send("/start")
    await harness.tap("Buy Number")
    await harness.tap("WhatsApp")

    assert "Show All" in " ".join(harness.buttons())


async def test_show_all_countries_lists_price_and_stock(harness):
    await harness.send("/start")
    await harness.tap("Buy Number")
    await harness.tap("WhatsApp")
    await harness.tap("Show All")

    assert "ALL COUNTRIES" in harness.text
    assert "India" in harness.text
    assert "₹11.00" in harness.text   # 1000 cost + 10% fee
    assert "120" in harness.text      # stock
    assert "+91" in harness.text      # dial code, looked up by name


async def test_a_listing_ends_with_a_way_back(harness):
    await harness.send("/start")
    await harness.tap("Buy Number")
    await harness.tap("Show All")

    assert "Back" in " ".join(harness.buttons())


async def test_show_all_countries_without_a_service_returns_to_the_picker(harness):
    """A stale button from a previous session must not blow up."""
    from app.bot.callbacks import Nav

    await harness.send("/start")
    await harness.press(Nav(to="countries_all").pack())

    assert "BUY NUMBER" in harness.text


async def test_the_smm_panel_offers_show_all(harness):
    await harness.send("/start")
    await harness.tap("SMM Panel")

    assert "Show All" in " ".join(harness.buttons())


async def test_show_all_smm_lists_rates(harness):
    await harness.send("/start")
    await harness.tap("SMM Panel")
    await harness.tap("Show All")

    assert "ALL SMM SERVICES" in harness.text
    assert "Instagram Followers" in harness.text
    assert "/1k" in harness.text


async def test_show_all_still_lets_you_buy(harness, session_factory):
    """Listing is a detour, not a dead end."""
    await harness.send("/start")
    await fund(session_factory, harness.user_id, 10_000)

    await harness.tap("Buy Number")
    await harness.tap("Show All")
    await harness.tap("Back")

    await harness.tap("WhatsApp")
    await harness.tap("India")
    await harness.tap("Confirm")

    assert "NUMBER PURCHASED" in harness.text


# -- the splitter -----------------------------------------------------------


def test_a_long_catalogue_is_split_into_several_messages():
    """Telegram caps a message at 4096 characters."""
    from app.bot.listing import paginate_lines

    lines = [f"🟢 <b>Country {i}</b> · ₹12.00 · 1,234" for i in range(400)]
    parts = paginate_lines(lines, "🗂 <b>ALL COUNTRIES</b>")

    assert len(parts) > 1
    assert all(len(part.body) < 4096 for part in parts)
    assert parts[0].body.startswith("🗂 <b>ALL COUNTRIES</b> 1/")


def test_lines_are_never_split_in_half():
    """A country's price cut across two messages would be unreadable."""
    from app.bot.listing import paginate_lines

    lines = [f"line-{i}-" + "x" * 100 for i in range(200)]
    parts = paginate_lines(lines, "H")

    rejoined = []
    for part in parts:
        rejoined.extend(part.body.split("\n\n", 1)[1].split("\n"))
    assert rejoined == lines


def test_a_short_catalogue_is_one_message_without_a_counter():
    from app.bot.listing import paginate_lines

    parts = paginate_lines(["only one"], "🗂 <b>ALL</b>")

    assert len(parts) == 1
    assert parts[0].is_only
    assert "1/1" not in parts[0].body


def test_an_empty_catalogue_produces_nothing():
    from app.bot.listing import paginate_lines

    assert paginate_lines([], "🗂 <b>ALL</b>") == []


def test_a_single_oversized_line_still_gets_its_own_message():
    from app.bot.listing import paginate_lines

    parts = paginate_lines(["x" * 5000, "short"], "H")
    assert len(parts) == 2


# -- dial codes -------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("India", "+91"),
        ("United Kingdom", "+44"),
        ("USA", "+1"),
        ("Hong Kong", "+852"),
        ("Czech Republic", "+420"),
        ("south africa", "+27"),
    ],
)
def test_dial_codes_are_matched_by_name(name, expected):
    from app.core.countries import dial_code

    assert dial_code(name) == expected


def test_an_unknown_country_shows_no_dial_code_rather_than_a_wrong_one():
    from app.core.countries import dial_code

    assert dial_code("Atlantis") == ""
    assert dial_code("") == ""
