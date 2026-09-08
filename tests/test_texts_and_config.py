"""Locale rendering and configuration validation."""

import pytest

from app.bot.texts import Safe, Texts
from app.core.config import ROOT_DIR, Settings
from app.core.exceptions import ConfigurationError


@pytest.fixture
def texts() -> Texts:
    return Texts(ROOT_DIR / "locales", "en")


def test_every_key_used_by_a_handler_exists(texts):
    """Guards against a locale key being renamed out from under a handler."""
    required = [
        "start.welcome", "start.returning", "buy.select_service", "buy.select_country",
        "buy.confirm", "buy.purchased", "sms.received", "sms.expired", "sms.cancelled",
        "sms.cancel_confirm", "sms.cancel_done", "rental.select_duration", "rental.confirm",
        "rental.created", "rental.message", "orders.root", "orders.list", "orders.detail",
        "favorites.list", "favorites.detail", "profile.main", "wallet.main", "wallet.invoice",
        "wallet.success", "wallet.history", "promo.prompt", "promo.success", "referral.main",
        "smm.main", "smm.confirm", "smm.created", "smm.status", "smm.finished",
        "help.main", "settings.main", "admin.panel", "admin.dashboard", "admin.health",
        "admin.user_detail", "admin.balance_done", "admin.broadcast_done", "admin.promo_created",
        "errors.generic", "errors.insufficient_balance", "errors.no_numbers",
        "errors.duplicate_operation", "errors.price_changed", "errors.maintenance",
        "policies.refund", "policies.terms", "policies.privacy",
    ]
    missing = [key for key in required if texts.get(key) == key]
    assert missing == [], f"missing locale keys: {missing}"


def test_placeholders_are_substituted(texts):
    rendered = texts.get("promo.success", code="X", amount="₹50", balance="₹100")
    assert "₹50" in rendered and "X" in rendered and "{" not in rendered


def test_untrusted_values_are_escaped(texts):
    """A service name from a provider must not be able to inject markup."""
    rendered = texts.get("buy.select_country", service="<b>evil</b>")
    assert "&lt;b&gt;evil&lt;/b&gt;" in rendered


def test_safe_values_pass_through(texts):
    rendered = texts.get("help.faq_refund", refund_policy=Safe("<i>ok</i>"))
    assert "<i>ok</i>" in rendered


def test_a_missing_key_degrades_to_the_key(texts):
    assert texts.get("nope.not.here") == "nope.not.here"


def test_a_missing_placeholder_does_not_crash(texts):
    assert texts.get("promo.success") != ""


# -- configuration ----------------------------------------------------------


def test_admin_ids_parse_from_a_comma_list(monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "111, 222,333")
    assert Settings().admin_ids == [111, 222, 333]


def test_first_admin_is_the_owner(monkeypatch):
    from app.core.constants import AdminRole

    monkeypatch.setenv("ADMIN_IDS", "111,222")
    settings = Settings()

    assert settings.role_for(111) is AdminRole.OWNER
    assert settings.role_for(222) is AdminRole.ADMIN
    assert settings.role_for(999) is None


def test_role_overrides_are_honoured(monkeypatch):
    from app.core.constants import AdminRole

    monkeypatch.setenv("ADMIN_IDS", "111,222")
    monkeypatch.setenv("ADMIN_ROLES", "222:finance")

    assert Settings().role_for(222) is AdminRole.FINANCE


def test_missing_sms_token_is_a_configuration_error(monkeypatch):
    monkeypatch.setenv("SMS_ACTIVATE_API_TOKEN", "")
    with pytest.raises(Exception, match="SMS_ACTIVATE_API_TOKEN"):
        Settings()


def test_smm_requires_url_and_key(monkeypatch):
    monkeypatch.setenv("SMM_ENABLED", "true")
    monkeypatch.setenv("SMM_API_URL", "")
    with pytest.raises(Exception, match="SMM_API_URL"):
        Settings()


def test_at_least_one_payment_provider_is_required(monkeypatch):
    monkeypatch.setenv("TELEGRAM_STARS_ENABLED", "false")
    monkeypatch.setenv("CRYPTOBOT_ENABLED", "false")
    with pytest.raises(Exception, match="payment provider"):
        Settings()


def test_get_settings_wraps_failures(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_IDS", "")
    with pytest.raises(ConfigurationError):
        get_settings()
    get_settings.cache_clear()


# -- permissions ------------------------------------------------------------


def test_roles_gate_privileged_actions():
    from app.core.constants import AdminRole
    from app.services.admin import can

    assert can(AdminRole.OWNER, "backup") is True
    assert can(AdminRole.SUPPORT, "balance") is False
    assert can(AdminRole.VIEWER, "broadcast") is False
    assert can(AdminRole.FINANCE, "balance") is True
    assert can(None, "dashboard") is False


def test_secrets_are_masked_for_logs():
    from app.core.logging import mask_secret

    assert mask_secret("abcdefghijklmnop") == "abcd…mnop"
    assert "secret" not in mask_secret("secret")
