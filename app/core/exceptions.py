"""Exception hierarchy.

Anything raised here carries a *message key* rather than user-facing text, so
the error middleware can render it through the locale files. Users never see a
traceback; the real exception is logged instead.
"""

from __future__ import annotations


class BotError(Exception):
    """Base class for every error the bot raises deliberately."""

    message_key = "errors.generic"

    def __init__(self, detail: str = "", **context: object) -> None:
        super().__init__(detail or self.message_key)
        self.detail = detail
        self.context = context


class ConfigurationError(BotError):
    """Configuration is missing or invalid -- raised at startup, never at runtime."""

    message_key = "errors.configuration"


class ProviderError(BotError):
    """An upstream provider failed."""

    message_key = "errors.provider_unavailable"


class ProviderAuthError(ProviderError):
    """Provider rejected our credentials. Fail fast, never retry."""

    message_key = "errors.provider_auth"


class ProviderRateLimitError(ProviderError):
    """Provider asked us to slow down."""

    message_key = "errors.provider_busy"


class NoNumbersAvailableError(ProviderError):
    """Provider has no numbers for this service/country right now."""

    message_key = "errors.no_numbers"


class InsufficientBalanceError(BotError):
    """User cannot afford the operation."""

    message_key = "errors.insufficient_balance"


class InsufficientProviderBalanceError(ProviderError):
    """*Our* provider account is out of funds -- an admin problem, not a user one."""

    message_key = "errors.provider_unavailable"


class OrderNotFoundError(BotError):
    message_key = "errors.order_not_found"


class AccessDeniedError(BotError):
    """The requesting user does not own this resource, or lacks the admin role."""

    message_key = "errors.access_denied"


class ValidationError(BotError):
    """User input did not pass validation."""

    message_key = "errors.invalid_input"


class PromoError(BotError):
    message_key = "errors.promo_invalid"


class DuplicateOperationError(BotError):
    """The same operation was submitted twice (double click, replayed webhook)."""

    message_key = "errors.duplicate_operation"


class StalePriceError(BotError):
    """The price moved between showing the quote and confirming it."""

    message_key = "errors.price_changed"


class MaintenanceError(BotError):
    message_key = "errors.maintenance"
