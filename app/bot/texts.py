"""Locale rendering.

Handlers never contain user-facing prose. They call ``texts.get("buy.confirm",
service=…)`` and the wording comes from ``locales/<lang>/messages.yaml``.

Substituted values are HTML-escaped by default, because most of them -- service
names, usernames, SMS bodies -- come from users or providers. Values that are
deliberately pre-formatted (a divider, a nested block we rendered ourselves)
are passed through :class:`Safe`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from app.core.logging import get_logger
from app.utils.formatting import DIVIDER, html_escape

logger = get_logger(__name__)


class Safe(str):
    """Marks a value as already-safe HTML, exempt from escaping."""


#: A custom-emoji placeholder in a locale file:
#: ``<tg-emoji id="buy">🛍</tg-emoji>``. The id is a *name* configured in
#: CUSTOM_EMOJI, not a Telegram id, so the same locale file works for every
#: operator. The tag's contents are the fallback shown to anyone whose client
#: will not render the custom emoji, and are what is left behind when no id is
#: configured at all.
EMOJI_MARKER = re.compile(r'<tg-emoji id="([a-z_]+)">(.*?)</tg-emoji>', re.S)


class Texts:
    """Loads message catalogues and renders keys with placeholders."""

    def __init__(
        self,
        locales_dir: Path,
        default_locale: str = "en",
        icons: dict[str, str] | None = None,
    ) -> None:
        self._locales_dir = locales_dir
        self._default = default_locale
        self._icons = icons or {}
        self._catalogues: dict[str, dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        """(Re)load every locale directory found under ``locales/``."""
        self._catalogues.clear()
        for path in sorted(self._locales_dir.glob("*/messages.yaml")):
            locale = path.parent.name
            with path.open(encoding="utf-8") as handle:
                self._catalogues[locale] = yaml.safe_load(handle) or {}
        if self._default not in self._catalogues:
            raise FileNotFoundError(
                f"No messages.yaml for default locale '{self._default}' in {self._locales_dir}"
            )
        logger.info("texts.loaded", locales=sorted(self._catalogues))

    @property
    def locales(self) -> list[str]:
        return sorted(self._catalogues)

    def get(self, key: str, locale: str | None = None, **values: Any) -> str:
        """Render ``key`` (dotted path) with ``values`` substituted."""
        template = self._lookup(key, locale)
        if template is None:
            logger.warning("texts.missing_key", key=key, locale=locale)
            return key
        return self.expand_emoji(self._format(template, values))

    def expand_emoji(self, text: str) -> str:
        """Turn locale emoji placeholders into real custom-emoji tags.

        Configured names become ``<tg-emoji emoji-id="...">`` for Telegram to
        render; unconfigured ones collapse to the plain fallback character, so
        a bot with no custom emoji set up still reads correctly.
        """

        def replace(match: re.Match[str]) -> str:
            name, fallback = match.group(1), match.group(2)
            emoji_id = self._icons.get(name)
            if not emoji_id:
                return fallback
            return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

        return EMOJI_MARKER.sub(replace, text)

    def button(self, name: str, locale: str | None = None, **values: Any) -> str:
        return self.get(f"buttons.{name}", locale, **values)

    def icon(self, name: str) -> str | None:
        """The custom emoji id configured for a named button, if any."""
        return self._icons.get(name)

    def _lookup(self, key: str, locale: str | None) -> str | None:
        for candidate in (locale or self._default, self._default):
            node: Any = self._catalogues.get(candidate)
            if node is None:
                continue
            for part in key.split("."):
                if not isinstance(node, dict) or part not in node:
                    node = None
                    break
                node = node[part]
            if isinstance(node, str):
                return node
        return None

    def _format(self, template: str, values: dict[str, Any]) -> str:
        payload = {
            name: (value if isinstance(value, Safe) else html_escape(value))
            for name, value in values.items()
        }
        payload.setdefault("divider", Safe(DIVIDER))
        try:
            return template.format(**payload).strip()
        except KeyError as exc:
            # A missing placeholder should degrade, not crash a user's screen.
            logger.warning("texts.missing_placeholder", placeholder=str(exc), template=template[:60])
            return template.strip()
