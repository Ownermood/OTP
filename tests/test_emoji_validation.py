"""Startup validation of the premium emoji registry -- must never crash the
bot, whatever Telegram says."""

from app.core.emoji_registry import default_icon_ids, validate_premium_emojis


class _WorkingBot:
    async def get_custom_emoji_stickers(self, custom_emoji_ids):
        return [object() for _ in custom_emoji_ids]


class _BrokenBot:
    async def get_custom_emoji_stickers(self, custom_emoji_ids):
        raise RuntimeError("network hiccup")


async def test_validation_reports_all_ids_found_when_telegram_confirms_them():
    found, total = await validate_premium_emojis(_WorkingBot())

    assert total == len(default_icon_ids())
    assert found == total


async def test_validation_never_raises_when_telegram_is_unreachable():
    """A network failure or a since-deleted pack must degrade gracefully,
    never crash startup."""
    found, total = await validate_premium_emojis(_BrokenBot())

    assert found == 0
    assert total == len(default_icon_ids())
