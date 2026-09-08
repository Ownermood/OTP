"""Entry point.

Startup is deliberately loud and fail-fast: configuration is validated, the
database is reachable, and every enabled provider is probed *before* the bot
starts accepting updates. A misconfigured bot refuses to run rather than
failing on a user's first purchase.
"""

from __future__ import annotations

import asyncio
import sys

from app.bot.setup import Application, build_application
from app.core.config import VERSION, Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger, setup_logging
from app.core.money import format_money
from app.database import check_connection

logger = get_logger(__name__)


async def preflight(app: Application) -> bool:
    """Verify everything the bot depends on. Returns False to abort startup."""
    settings = app.settings
    ok = True

    if not await check_connection(app.engine):
        logger.error("startup.database_unreachable", url=_safe_url(settings.database_url))
        return False
    logger.info("startup.check", component="database", status="connected")

    try:
        balance = await app.sms_provider.get_balance()
        logger.info(
            "startup.check",
            component=f"sms:{app.sms_provider.name}",
            status="connected",
            balance=format_money(balance, settings.currency_symbol),
        )
    except Exception as exc:
        logger.error("startup.sms_provider_failed", provider=app.sms_provider.name, error=str(exc))
        ok = False

    for name, provider in app.payment_providers.items():
        if await provider.health_check():
            logger.info("startup.check", component=f"payment:{name}", status="connected")
        else:
            logger.error("startup.payment_provider_failed", provider=name)
            ok = False

    if app.smm_provider is not None:
        if await app.smm_provider.health_check():
            logger.info("startup.check", component="smm", status="connected")
        else:
            logger.error("startup.smm_provider_failed")
            ok = False

    return ok


async def run(settings: Settings) -> int:
    app = build_application(settings)

    try:
        me = await app.bot.get_me()
    except Exception as exc:
        logger.error("startup.telegram_failed", error=str(exc))
        await app.shutdown()
        return 1

    if not await preflight(app):
        await app.shutdown()
        return 1

    _banner(settings, me.username)
    for worker in app.workers:
        worker.start()

    try:
        await app.dispatcher.start_polling(app.bot, allowed_updates=None)
    finally:
        await app.shutdown()
    return 0


def _banner(settings: Settings, username: str) -> None:
    """Startup summary. Never prints a credential."""
    logger.info(
        "startup.ready",
        version=VERSION,
        bot=f"@{username}",
        service=settings.service_name,
        sms_provider=settings.sms_provider,
        payments=[
            name
            for name, enabled in (
                ("cryptobot", settings.cryptobot_enabled),
                ("telegram_stars", settings.telegram_stars_enabled),
            )
            if enabled
        ],
        smm=settings.smm_enabled,
        admins=len(settings.admin_ids),
    )


def _safe_url(url: str) -> str:
    """Strip credentials out of a database URL before it reaches a log."""
    if "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    return f"{scheme}://***@{rest.split('@', 1)[1]}"


def main() -> int:
    try:
        settings = get_settings()
    except ConfigurationError as exc:
        # Logging is not configured yet, so this goes straight to stderr.
        print(f"\n❌ {exc}\n", file=sys.stderr)
        return 2

    setup_logging(settings.log_level, settings.log_json)
    try:
        return asyncio.run(run(settings))
    except KeyboardInterrupt:
        logger.info("shutdown.interrupted")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
