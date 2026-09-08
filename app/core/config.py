"""Configuration.

Everything configurable lives in the environment. No credential, URL or
business number is hardcoded anywhere else in the codebase, and the settings
object is validated at startup so the bot refuses to run half-configured
rather than failing on a user's first purchase.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.constants import AdminRole
from app.core.exceptions import ConfigurationError

VERSION = "3.0.0"
ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Typed view over the ``.env`` file."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- Telegram -------------------------------------------------------
    bot_token: str = Field(min_length=20)
    parse_mode: str = "HTML"

    # --- Admins ---------------------------------------------------------
    #: Comma-separated Telegram IDs. The first one is treated as the OWNER.
    # NoDecode: these arrive as plain comma-separated strings, not JSON.
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    #: Optional per-id role overrides, e.g. ``123:finance,456:support``.
    admin_roles: Annotated[dict[int, AdminRole], NoDecode] = Field(default_factory=dict)

    # --- Branding / business -------------------------------------------
    service_name: str = "SMS Marketplace"
    currency_symbol: str = "₹"
    currency_code: str = "INR"
    support_username: str = ""
    support_response_time: str = "5-15 minutes"

    # --- Pricing --------------------------------------------------------
    #: Percentage markup added on top of the provider price.
    service_fee_percent: Decimal = Decimal("5")
    #: Flat markup in *major* units added after the percentage.
    service_fee_fixed: Decimal = Decimal("0")
    #: Clamp for the final user-facing price, in major units. 0 disables.
    min_price: Decimal = Decimal("0")
    max_price: Decimal = Decimal("0")
    #: Exchange rate used to convert provider currency into ours.
    provider_currency_rate: Decimal = Decimal("1")

    # --- SMS provider ---------------------------------------------------
    sms_provider: str = "sms_activate"
    sms_activate_api_token: str = ""
    sms_activate_base_url: str = "https://api.sms-activate.guru/"
    sms_poll_interval: int = 5
    sms_timeout: int = 900
    sms_provider_low_balance_threshold: Decimal = Decimal("10")

    # --- SMM provider ---------------------------------------------------
    smm_enabled: bool = False
    smm_provider: str = "generic"
    smm_api_url: str = ""
    smm_api_key: str = ""
    smm_markup_percent: Decimal = Decimal("20")
    smm_poll_interval: int = 60

    # --- Payments -------------------------------------------------------
    cryptobot_enabled: bool = False
    cryptobot_api_token: str = ""
    cryptobot_base_url: str = "https://pay.crypt.bot/api/"
    cryptobot_asset: str = "USDT"
    #: How many major units one unit of ``cryptobot_asset`` is worth.
    cryptobot_rate: Decimal = Decimal("90")

    telegram_stars_enabled: bool = False
    #: How many major units one Telegram Star is worth.
    telegram_stars_rate: Decimal = Decimal("2.15")
    telegram_stars_max: int = 2500

    # --- Manual (UPI / bank transfer) deposits --------------------------
    manual_payment_enabled: bool = False
    #: Channel where requests are posted for review. The bot must be an admin
    #: there, and reviewers must be listed in ADMIN_IDS / ADMIN_ROLES.
    manual_payment_channel_id: int = 0
    #: How many un-reviewed requests one user may have open at a time.
    manual_payment_max_pending: int = 3

    payment_timeout_minutes: int = 10
    #: How long past its expiry an unreported invoice is still polled, so a
    #: payment made during a restart is not written off with the money taken.
    payment_grace_hours: int = 24
    min_deposit: Decimal = Decimal("50")
    max_deposit: Decimal = Decimal("50000")

    # --- Referral -------------------------------------------------------
    referral_enabled: bool = True
    referral_percent: Decimal = Decimal("10")
    referral_min_deposit: Decimal = Decimal("0")

    # --- Features -------------------------------------------------------
    rental_enabled: bool = True
    transfer_enabled: bool = False
    min_rental_hours: int = 4
    max_rental_hours: int = 720
    maintenance_mode: bool = False

    # --- Infrastructure -------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///data/bot.db"
    locale: str = "en"
    locales_dir: str = "locales"
    log_level: str = "INFO"
    log_json: bool = False
    http_timeout: float = 20.0
    http_retries: int = 3
    #: Max callback/message events accepted per user per second.
    rate_limit_per_second: float = 3.0
    cache_ttl_seconds: int = 300

    # --- Validators -----------------------------------------------------

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in _split_csv(value)]
        return value

    @field_validator("admin_roles", mode="before")
    @classmethod
    def _parse_admin_roles(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        roles: dict[int, AdminRole] = {}
        for part in _split_csv(value):
            if ":" not in part:
                raise ValueError("ADMIN_ROLES must look like '123:finance,456:support'")
            raw_id, raw_role = part.split(":", 1)
            roles[int(raw_id)] = AdminRole(raw_role.strip().lower())
        return roles

    @field_validator("parse_mode")
    @classmethod
    def _check_parse_mode(cls, value: str) -> str:
        allowed = {"HTML", "MarkdownV2", "Markdown"}
        if value not in allowed:
            raise ValueError(f"PARSE_MODE must be one of {sorted(allowed)}")
        return value

    @field_validator("support_username")
    @classmethod
    def _strip_at(cls, value: str) -> str:
        return value.lstrip("@")

    @model_validator(mode="after")
    def _check_dependent_settings(self) -> Settings:
        if self.sms_provider == "sms_activate" and not self.sms_activate_api_token:
            raise ValueError("SMS_ACTIVATE_API_TOKEN is required when SMS_PROVIDER=sms_activate")
        if self.cryptobot_enabled and not self.cryptobot_api_token:
            raise ValueError("CRYPTOBOT_API_TOKEN is required when CRYPTOBOT_ENABLED=true")
        if self.smm_enabled and not (self.smm_api_url and self.smm_api_key):
            raise ValueError("SMM_API_URL and SMM_API_KEY are required when SMM_ENABLED=true")
        if not self.admin_ids:
            raise ValueError("ADMIN_IDS must contain at least one Telegram user id")
        if self.min_rental_hours > self.max_rental_hours:
            raise ValueError("MIN_RENTAL_HOURS cannot exceed MAX_RENTAL_HOURS")
        if self.min_deposit > self.max_deposit:
            raise ValueError("MIN_DEPOSIT cannot exceed MAX_DEPOSIT")
        if self.manual_payment_enabled and not self.manual_payment_channel_id:
            raise ValueError(
                "MANUAL_PAYMENT_CHANNEL_ID is required when MANUAL_PAYMENT_ENABLED=true"
            )
        if not any(
            (self.cryptobot_enabled, self.telegram_stars_enabled, self.manual_payment_enabled)
        ):
            raise ValueError("Enable at least one payment provider")
        return self

    # --- Derived helpers ------------------------------------------------

    def role_for(self, user_id: int) -> AdminRole | None:
        """Return the admin role for ``user_id``, or ``None`` if not an admin."""
        if user_id in self.admin_roles:
            return self.admin_roles[user_id]
        if user_id in self.admin_ids:
            return AdminRole.OWNER if user_id == self.admin_ids[0] else AdminRole.ADMIN
        return None

    @property
    def locales_path(self) -> Path:
        path = Path(self.locales_dir)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def support_url(self) -> str:
        return f"https://t.me/{self.support_username}" if self.support_username else ""


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache settings, re-raising validation problems as ConfigurationError."""
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:  # pydantic ValidationError, ValueError, ...
        raise ConfigurationError(_format_validation_error(exc)) from exc


def _format_validation_error(exc: Exception) -> str:
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return str(exc)
    lines = []
    for error in errors():
        field = ".".join(str(part) for part in error.get("loc", ())) or "config"
        lines.append(f"  - {field.upper()}: {error.get('msg', 'invalid')}")
    return "Configuration error:\n" + "\n".join(lines)
