"""The premium custom-emoji registry.

Every id must be traceable to the real Telegram extraction in
data/all_premium_emojis.json -- nothing here may be invented.
"""

import json
from pathlib import Path

from app.core.config import ROOT_DIR
from app.core.emoji_registry import PREMIUM_EMOJI, default_icon_ids

EXPECTED_ROLES = {
    "home", "buy", "country", "service", "search", "balance", "deposit",
    "payment", "orders", "order", "account", "referral", "support", "help",
    "success", "error", "warning", "loading", "refresh", "back", "cancel",
    "confirm", "phone", "otp", "copy", "admin", "statistics", "pending",
    "completed", "expired",
}


def _extracted_ids() -> set[str]:
    path = ROOT_DIR / "data" / "all_premium_emojis.json"
    with open(path, encoding="utf-8") as f:
        return {entry["custom_emoji_id"] for entry in json.load(f)}


def test_every_required_semantic_role_is_present():
    assert set(PREMIUM_EMOJI) == EXPECTED_ROLES


def test_every_verified_id_was_actually_extracted_from_an_approved_pack():
    """The hard rule: no invented ids. Every verified id must trace back to
    the real getStickerSet extraction, not be typed in by hand."""
    extracted = _extracted_ids()
    for role, entry in PREMIUM_EMOJI.items():
        if entry.verified:
            assert entry.custom_emoji_id in extracted, f"{role}: id not found in extraction"
            assert entry.pack is not None


def test_every_verified_id_is_purely_numeric():
    for role, entry in PREMIUM_EMOJI.items():
        if entry.verified:
            assert entry.custom_emoji_id.isdigit(), f"{role}: {entry.custom_emoji_id!r}"


def test_no_two_roles_share_the_same_custom_emoji_id():
    ids = [e.custom_emoji_id for e in PREMIUM_EMOJI.values() if e.verified]
    assert len(ids) == len(set(ids))


def test_every_role_has_a_non_empty_fallback_even_when_unverified():
    for role, entry in PREMIUM_EMOJI.items():
        assert entry.fallback, f"{role} has no fallback"
        if not entry.verified:
            assert entry.custom_emoji_id is None


def test_unverified_roles_are_not_silently_promoted():
    """back/copy have no good match in the approved packs -- they must stay
    fallback-only rather than being forced onto an unrelated icon."""
    assert PREMIUM_EMOJI["back"].verified is False
    assert PREMIUM_EMOJI["copy"].verified is False


def test_default_icon_ids_only_includes_verified_roles():
    icons = default_icon_ids()
    assert "back" not in icons
    assert "copy" not in icons
    assert icons["buy"] == PREMIUM_EMOJI["buy"].custom_emoji_id
    assert len(icons) == sum(1 for e in PREMIUM_EMOJI.values() if e.verified)


def test_the_raw_extraction_file_exists_and_covers_all_five_packs():
    path = Path(ROOT_DIR) / "data" / "all_premium_emojis.json"
    assert path.exists()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    packs = {entry["pack"] for entry in data}
    assert packs == {
        "SoLo_HaMiD", "AnimatedIconic", "getmodpc",
        "CenterOfEmoji22890889", "vector_icons_by_fStikBot",
    }
    assert len(data) > 500  # the real extraction pulled 702 entries
    for entry in data:
        assert entry["custom_emoji_id"].isdigit()
        assert entry["file_id"]
