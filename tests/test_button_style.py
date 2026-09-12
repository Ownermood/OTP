"""Button styling.

Bot API 9.4 made colour a real property of a button. These tests are about the
colour meaning the same thing everywhere: one success per screen, danger on
anything irreversible or money-moving, and nothing invented outside the three
values Telegram accepts.
"""

import pytest

from app.bot import keyboards
from app.bot.keyboards.style import DANGER, PRIMARY, SUCCESS, button
from app.bot.texts import Texts
from app.core.config import ROOT_DIR

VALID_STYLES = {SUCCESS, DANGER, PRIMARY, None}


@pytest.fixture
def texts() -> Texts:
    return Texts(ROOT_DIR / "locales", "en")


def _flat(markup):
    return [b for row in markup.inline_keyboard for b in row]


def _styles(markup) -> list[str | None]:
    return [b.style for b in _flat(markup)]


# -- the helper -------------------------------------------------------------


def test_a_styled_button_carries_its_style():
    assert button("Go", callback_data="x", style=SUCCESS).style == "success"


def test_an_unstyled_button_sends_no_style():
    """Omitting it leaves the client's own default, which is the point."""
    packed = button("Back", callback_data="x").model_dump(exclude_none=True)
    assert "style" not in packed


def test_a_custom_emoji_is_attached_when_given():
    packed = button("Buy", callback_data="x", icon="5350513667437440642").model_dump(
        exclude_none=True
    )
    assert packed["icon_custom_emoji_id"] == "5350513667437440642"


def test_no_custom_emoji_key_without_one():
    assert "icon_custom_emoji_id" not in button("Buy", callback_data="x").model_dump(
        exclude_none=True
    )


# -- the screens ------------------------------------------------------------


def test_every_style_used_is_one_telegram_accepts(texts):
    """A typo'd style is rejected by Telegram at send time, not at build time."""
    screens = [
        keyboards.main_menu(texts, "en", True),
        keyboards.purchase_confirm(texts, "en", "tok"),
        keyboards.cancel_confirm(texts, "en", 1),
        keyboards.wallet(texts, "en", True),
        keyboards.invoice(texts, "en", 1, "https://pay.test"),
        keyboards.profile(texts, "en"),
        keyboards.orders_root(texts, "en", True),
        keyboards.back_home(texts, "en"),
    ]
    for markup in screens:
        for style in _styles(markup):
            assert style in VALID_STYLES, f"unknown style {style!r}"


def test_the_main_menu_highlights_exactly_one_action(texts):
    """If everything is green, nothing is."""
    assert _styles(keyboards.main_menu(texts, "en", True)).count(SUCCESS) == 1


def test_buying_is_the_highlighted_action(texts):
    buttons = _flat(keyboards.main_menu(texts, "en", True))
    success = next(b for b in buttons if b.style == SUCCESS)
    assert "buy" in success.text.lower()


def test_balance_navigation_carries_no_style(texts):
    """Per style.py: plain balance/wallet navigation is unstyled, not danger."""
    wallet_button = next(
        b for b in _flat(keyboards.main_menu(texts, "en", True)) if "balance" in b.text.lower()
    )
    assert wallet_button.style is None


def test_add_balance_is_primary_not_danger(texts):
    """Topping up is money arriving; danger there reads as a warning against it."""
    deposit = next(
        b for b in _flat(keyboards.wallet(texts, "en", False)) if "add balance" in b.text.lower()
    )
    assert deposit.style == PRIMARY


def test_confirming_a_purchase_is_success_and_cancelling_is_danger(texts):
    buttons = _flat(keyboards.purchase_confirm(texts, "en", "tok"))
    by_style = {b.style: b.text.lower() for b in buttons}

    assert "confirm" in by_style[SUCCESS]
    assert "cancel" in by_style[DANGER]


def test_the_destructive_choice_is_red_even_when_it_says_yes(texts):
    """On a cancel screen, 'Yes, cancel' is the dangerous one, not 'Keep'."""
    buttons = _flat(keyboards.cancel_confirm(texts, "en", 1))
    danger = next(b for b in buttons if b.style == DANGER)
    success = next(b for b in buttons if b.style == SUCCESS)

    assert "yes, cancel" in danger.text.lower()
    assert "keep" in success.text.lower()


def test_paying_is_the_highlighted_action_on_an_invoice(texts):
    buttons = _flat(keyboards.invoice(texts, "en", 1, "https://pay.test"))
    assert next(b for b in buttons if b.style == SUCCESS).text.lower().endswith("pay now")


def test_navigation_is_never_success(texts):
    """Back and Home must not compete with the action a screen is for."""
    for markup in (keyboards.back_home(texts, "en"), keyboards.back_home(texts, "en", "wallet")):
        assert SUCCESS not in _styles(markup)


# -- custom emoji from config ----------------------------------------------


def test_configured_icons_reach_the_buttons():
    texts = Texts(ROOT_DIR / "locales", "en", {"buy": "5350513667437440642"})
    buy = next(
        b for b in _flat(keyboards.main_menu(texts, "en", True)) if "buy" in b.text.lower()
    )
    assert buy.icon_custom_emoji_id == "5350513667437440642"


def test_buttons_render_without_configured_icons(texts):
    assert all(b.icon_custom_emoji_id is None for b in _flat(keyboards.main_menu(texts, "en", True)))


def test_icons_parse_from_the_environment(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("CUSTOM_EMOJI", "buy:5350513667437440642, wallet:5352640560718949874")
    assert Settings().custom_emoji == {
        "buy": "5350513667437440642",
        "wallet": "5352640560718949874",
    }


def test_a_malformed_icon_setting_is_refused_at_startup(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("CUSTOM_EMOJI", "buy")
    with pytest.raises(Exception, match="CUSTOM_EMOJI"):
        Settings()


def test_a_non_numeric_emoji_id_is_refused(monkeypatch):
    """Telegram ids are numeric; a pasted emoji character would silently fail."""
    from app.core.config import Settings

    monkeypatch.setenv("CUSTOM_EMOJI", "buy:🛍")
    with pytest.raises(Exception, match="custom emoji id"):
        Settings()


# -- custom emoji in message text ------------------------------------------


def test_a_marker_becomes_a_real_tag_when_configured():
    texts = Texts(ROOT_DIR / "locales", "en", {"buy": "5350513667437440642"})

    rendered = texts.expand_emoji('<tg-emoji id="buy">🛍</tg-emoji> Buy')

    assert rendered == '<tg-emoji emoji-id="5350513667437440642">🛍</tg-emoji> Buy'


def test_a_marker_falls_back_to_the_plain_character(texts):
    """A bot with no custom emoji configured must still read correctly."""
    assert texts.expand_emoji('<tg-emoji id="buy">🛍</tg-emoji> Buy') == "🛍 Buy"


def test_an_unconfigured_name_falls_back_too():
    texts = Texts(ROOT_DIR / "locales", "en", {"buy": "5350513667437440642"})

    assert texts.expand_emoji('<tg-emoji id="other">❓</tg-emoji>') == "❓"


def test_several_markers_in_one_message_are_all_expanded():
    texts = Texts(ROOT_DIR / "locales", "en", {"a": "111", "b": "222"})

    rendered = texts.expand_emoji('<tg-emoji id="a">1</tg-emoji> and <tg-emoji id="b">2</tg-emoji>')

    assert rendered == (
        '<tg-emoji emoji-id="111">1</tg-emoji> and <tg-emoji emoji-id="222">2</tg-emoji>'
    )


def test_text_without_markers_is_untouched(texts):
    assert texts.expand_emoji("plain <b>text</b>") == "plain <b>text</b>"


def test_the_welcome_screen_expands_its_markers():
    """End to end through get(), not just the helper."""
    texts = Texts(ROOT_DIR / "locales", "en", {"welcome": "5350513667437440642"})

    rendered = texts.get("start.welcome", service_name="Shop", smm_line="")

    assert '<tg-emoji emoji-id="5350513667437440642">⚡️</tg-emoji>' in rendered


def test_the_welcome_screen_reads_fine_without_them(texts):
    rendered = texts.get("start.welcome", service_name="Shop", smm_line="")

    assert "tg-emoji" not in rendered
    assert "⚡️" in rendered


def test_no_locale_string_leaves_a_raw_marker_behind(texts):
    """Every marker in every locale file must expand or fall back, never leak."""
    import yaml

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, str):
            yield node

    with open(ROOT_DIR / "locales" / "en" / "messages.yaml", encoding="utf-8") as handle:
        catalogue = yaml.safe_load(handle)

    for raw in walk(catalogue):
        assert 'id="' not in texts.expand_emoji(raw), f"marker survived: {raw[:60]}"
