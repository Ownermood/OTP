"""Semantic premium custom-emoji registry.

Every ``custom_emoji_id`` below was extracted directly from Telegram via
``getStickerSet`` against the five owner-approved packs (SoLo_HaMiD,
AnimatedIconic, getmodpc, CenterOfEmoji22890889, vector_icons_by_fStikBot) --
never invented. The full raw extraction (702 entries) lives in
``data/all_premium_emojis.json``; the curated selection evidence (which role
picked which id, and why) lives in ``data/selected_premium_emojis.json``.

A role with no visually appropriate match in the verified packs is left
``verified=False`` with only a Unicode fallback, rather than forcing a
mismatched icon onto it (``back`` and ``copy``, currently).

This feeds :class:`app.bot.texts.Texts` as its default icon set -- see
``default_icon_ids()`` -- so handlers keep requesting icons by semantic name
(``texts.icon("buy")``) exactly as before. Nothing here changes how a missing
or invalid id degrades: :mod:`app.bot.texts` already falls back to the
Unicode content of the ``<tg-emoji>`` marker, and Telegram itself falls back
further to plain text if a client cannot render custom emoji at all.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmojiEntry:
    custom_emoji_id: str | None
    fallback: str
    pack: str | None
    verified: bool


PREMIUM_EMOJI: dict[str, EmojiEntry] = {
    "home": EmojiEntry("5897974332113554932", "🏠", "CenterOfEmoji22890889", True),
    "buy": EmojiEntry("6339201691140758295", "🛍️", "getmodpc", True),
    "country": EmojiEntry("5895665559558689321", "🌍", "CenterOfEmoji22890889", True),
    "service": EmojiEntry("5895577117592128901", "⚙️", "CenterOfEmoji22890889", True),
    "search": EmojiEntry("6053117952528493140", "🔍", "getmodpc", True),
    "balance": EmojiEntry("5116648080787112958", "💰", "SoLo_HaMiD", True),
    "deposit": EmojiEntry("6339079894458179573", "➕", "getmodpc", True),
    "payment": EmojiEntry("5134438483867206614", "💱", "SoLo_HaMiD", True),
    "orders": EmojiEntry("5093658078629332101", "📦", "AnimatedIconic", True),
    "order": EmojiEntry("5093874368887390961", "📌", "AnimatedIconic", True),
    "account": EmojiEntry("5116582462276764538", "👤", "SoLo_HaMiD", True),
    "referral": EmojiEntry("5895347444215975839", "🎁", "CenterOfEmoji22890889", True),
    "support": EmojiEntry("5093749995224433426", "💬", "AnimatedIconic", True),
    "help": EmojiEntry("5116240346656801621", "❓", "SoLo_HaMiD", True),
    "success": EmojiEntry("5096229960880751226", "✅", "AnimatedIconic", True),
    "error": EmojiEntry("5895714560840568825", "❌", "CenterOfEmoji22890889", True),
    "warning": EmojiEntry("5096372669759095585", "⚠️", "AnimatedIconic", True),
    "loading": EmojiEntry("6053323501073341449", "⌛", "getmodpc", True),
    "refresh": EmojiEntry("6053225373955530616", "🔄", "getmodpc", True),
    "back": EmojiEntry(None, "🔙", None, False),
    "cancel": EmojiEntry("5116151848855667552", "🚫", "SoLo_HaMiD", True),
    "confirm": EmojiEntry("5895388272175091031", "✔️", "CenterOfEmoji22890889", True),
    "phone": EmojiEntry("6053064918272318713", "📱", "getmodpc", True),
    "otp": EmojiEntry("5895685239098838464", "🔐", "CenterOfEmoji22890889", True),
    "copy": EmojiEntry(None, "📋", None, False),
    "admin": EmojiEntry("5895227687642861193", "👑", "CenterOfEmoji22890889", True),
    "statistics": EmojiEntry("6053216517732964810", "📈", "getmodpc", True),
    "pending": EmojiEntry("5895443668663275064", "🟡", "CenterOfEmoji22890889", True),
    "completed": EmojiEntry("6053400449707416241", "🟢", "getmodpc", True),
    "expired": EmojiEntry("6053134711490878159", "🔴", "getmodpc", True),
}


def default_icon_ids() -> dict[str, str]:
    """``role -> custom_emoji_id`` for every verified entry.

    Feeds :class:`Texts` as its default icon set. ``CUSTOM_EMOJI`` in
    ``.env`` is layered on top of this (see ``build_application``), so an
    operator can still override or add roles without code changes.
    """
    return {name: entry.custom_emoji_id for name, entry in PREMIUM_EMOJI.items() if entry.verified}


async def validate_premium_emojis(bot) -> tuple[int, int]:
    """Re-confirm the registry's ids still resolve on Telegram, at startup.

    A pack owner can edit or delete a pack after this registry was built, so
    this is checked again on every start rather than trusted forever. Never
    raises and never blocks startup: a network hiccup or a since-deleted
    pack degrades to "fewer premium icons render", not a crashed bot. Logs
    only counts -- no ids, no token, no other secret.
    """
    ids = list(default_icon_ids().values())
    if not ids:
        return 0, 0
    try:
        found = await bot.get_custom_emoji_stickers(custom_emoji_ids=ids)
        return len(found), len(ids)
    except Exception:
        return 0, len(ids)
