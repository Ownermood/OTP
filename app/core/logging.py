"""Structured logging.

Credentials never reach the log: :func:`mask_secret` is the only approved way
to mention a token, and the processor chain scrubs known-sensitive keys.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

#: Keys whose values are dropped before a log line is rendered.
SENSITIVE_KEYS = frozenset(
    {
        "api_key", "api_token", "token", "bot_token", "password", "secret",
        "authorization", "crypto_pay_api_token", "smm_api_key", "key",
    }
)


def mask_secret(value: str) -> str:
    """Render a credential as ``abcd…wxyz`` so logs can identify it, not reuse it."""
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def _scrub(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "<redacted>"
    return event_dict


def setup_logging(level: str = "INFO", json_output: bool = False) -> None:
    """Configure structlog + stdlib logging once, at startup."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)

    renderer = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _scrub,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level.upper())
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger, conventionally named after the calling module."""
    return structlog.get_logger(name)
