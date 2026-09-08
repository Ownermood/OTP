"""Provider registry.

Adding a provider means writing an adapter and registering it here. Nothing
else in the codebase needs to change.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.providers.base import BasePaymentProvider, BaseSMMProvider, BaseSMSProvider
from app.providers.cryptobot import CryptoBotProvider
from app.providers.smm import GenericSmmProvider
from app.providers.sms_activate import SmsActivateProvider
from app.providers.telegram_stars import TelegramStarsProvider
from app.providers.temporasms import TemporaSmsProvider


def build_sms_provider(settings: Settings) -> BaseSMSProvider:
    """Instantiate the SMS provider named by ``SMS_PROVIDER``."""
    adapters: dict[str, type[BaseSMSProvider]] = {
        SmsActivateProvider.name: SmsActivateProvider,
        TemporaSmsProvider.name: TemporaSmsProvider,
    }
    adapter = adapters.get(settings.sms_provider)
    if adapter is None:
        raise ConfigurationError(f"Unknown SMS_PROVIDER: {settings.sms_provider}")
    return adapter(
        api_key=settings.sms_activate_api_token,
        base_url=settings.sms_activate_base_url,
        currency_rate=settings.provider_currency_rate,
        timeout=settings.http_timeout,
        retries=settings.http_retries,
    )


def build_payment_providers(settings: Settings) -> dict[str, BasePaymentProvider]:
    """Instantiate every enabled payment provider, keyed by provider name."""
    providers: dict[str, BasePaymentProvider] = {}
    if settings.cryptobot_enabled:
        providers[CryptoBotProvider.name] = CryptoBotProvider(
            api_token=settings.cryptobot_api_token,
            base_url=settings.cryptobot_base_url,
            asset=settings.cryptobot_asset,
            rate=settings.cryptobot_rate,
            timeout_minutes=settings.payment_timeout_minutes,
            timeout=settings.http_timeout,
        )
    if settings.telegram_stars_enabled:
        providers[TelegramStarsProvider.name] = TelegramStarsProvider(
            rate=settings.telegram_stars_rate,
            max_stars=settings.telegram_stars_max,
            timeout_minutes=settings.payment_timeout_minutes,
        )
    return providers


def build_smm_provider(settings: Settings) -> BaseSMMProvider | None:
    """Instantiate the SMM provider, or ``None`` when the module is disabled."""
    if not settings.smm_enabled:
        return None
    if settings.smm_provider == "generic":
        return GenericSmmProvider(
            api_url=settings.smm_api_url,
            api_key=settings.smm_api_key,
            currency_rate=settings.provider_currency_rate,
            timeout=settings.http_timeout,
        )
    raise ConfigurationError(f"Unknown SMM_PROVIDER: {settings.smm_provider}")
