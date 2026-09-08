"""Short-lived callback tokens.

Telegram limits callback data to 64 bytes, and any value embedded in it is
attacker-controlled. So callbacks carry an opaque token -- ``buy:a1b2c3`` --
and the real payload (service, country, quoted price) is kept server-side and
looked up by that token. A user can only redeem their own tokens.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any

#: Tokens outlive a quote screen but not a session.
DEFAULT_TTL = 900


@dataclass(slots=True)
class _Entry:
    user_id: int
    payload: dict[str, Any]
    expires_at: float
    consumed: bool = field(default=False)


class TokenStore:
    """In-memory store mapping short tokens to server-side payloads."""

    def __init__(self, ttl: int = DEFAULT_TTL) -> None:
        self._ttl = ttl
        self._entries: dict[str, _Entry] = {}

    def issue(self, user_id: int, **payload: Any) -> str:
        """Store ``payload`` for ``user_id`` and return its token."""
        self._evict_expired()
        token = secrets.token_urlsafe(6)
        self._entries[token] = _Entry(user_id, payload, time.monotonic() + self._ttl)
        return token

    def peek(self, token: str, user_id: int) -> dict[str, Any] | None:
        """Read a token's payload without consuming it. Returns ``None`` if invalid."""
        entry = self._entries.get(token)
        if entry is None or entry.user_id != user_id or entry.expires_at < time.monotonic():
            return None
        return entry.payload

    def consume(self, token: str, user_id: int) -> dict[str, Any] | None:
        """Redeem a token exactly once.

        A second redemption returns ``None``, which is what makes a
        double-tapped confirm button harmless.
        """
        entry = self._entries.get(token)
        if entry is None or entry.user_id != user_id or entry.expires_at < time.monotonic():
            return None
        if entry.consumed:
            return None
        entry.consumed = True
        return entry.payload

    def _evict_expired(self) -> None:
        now = time.monotonic()
        for token in [t for t, e in self._entries.items() if e.expires_at < now]:
            del self._entries[token]
