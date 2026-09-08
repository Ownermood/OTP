"""Input validation. Every piece of user-typed text passes through here."""

from __future__ import annotations

import re

from app.core.exceptions import ValidationError

USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
PROMO_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)


def clean_search_query(text: str, max_length: int = 32) -> str:
    """Normalise a search term: trimmed, collapsed, lower-cased, length-capped."""
    cleaned = re.sub(r"\s+", " ", text.strip())[:max_length].lower()
    if len(cleaned) < 1:
        raise ValidationError("search query is empty")
    return cleaned


def parse_username(text: str) -> str:
    """Validate a Telegram username, returning it without the leading ``@``."""
    candidate = text.strip().lstrip("@")
    if not USERNAME_RE.match(candidate):
        raise ValidationError("invalid username")
    return candidate


def parse_promo_code(text: str) -> str:
    """Validate and normalise a promo code to upper case."""
    candidate = text.strip().upper()
    if not PROMO_RE.match(candidate):
        raise ValidationError("invalid promo code")
    return candidate


def parse_positive_int(text: str, minimum: int = 1, maximum: int | None = None) -> int:
    """Parse a bounded positive integer from user input."""
    candidate = text.strip().replace(" ", "")
    if not candidate.isdigit():
        raise ValidationError("not a number")
    value = int(candidate)
    if value < minimum or (maximum is not None and value > maximum):
        raise ValidationError("out of range")
    return value


def parse_link(text: str) -> str:
    """Validate an SMM order target link."""
    candidate = text.strip()
    if len(candidate) > 512 or not URL_RE.match(candidate):
        raise ValidationError("invalid link")
    return candidate
