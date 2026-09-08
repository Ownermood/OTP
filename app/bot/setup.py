"""Application wiring.

Builds every long-lived object once, injects it into the dispatcher's workflow
data (so handlers receive it as a keyword argument), registers middlewares in
the order documented in :mod:`app.bot.middlewares`, and starts the workers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.bot.handlers import build_router
from app.bot.middlewares import (
    DatabaseMiddleware,
    ErrorMiddleware,
    MaintenanceMiddleware,
    ThrottleMiddleware,
    UserMiddleware,
)
from app.bot.texts import Texts
from app.core.config import Settings
from app.core.logging import get_logger
from app.database import create_engine, create_session_factory
from app.providers import build_payment_providers, build_smm_provider, build_sms_provider
from app.providers.base import BasePaymentProvider, BaseSMMProvider, BaseSMSProvider
from app.services.catalog import CatalogService
from app.services.notifications import NotificationService
from app.services.pricing import PricingService
from app.services.workers import HealthWorker, PaymentWorker, SmmWorker, SmsWorker
from app.utils.cache import TTLCache
from app.utils.tokens import TokenStore

logger = get_logger(__name__)


@dataclass(slots=True)
class Application:
    """Everything the process owns, so shutdown can close all of it."""

    settings: Settings
    bot: Bot
    dispatcher: Dispatcher
    engine: AsyncEngine
    session_factory: async_sessionmaker
    texts: Texts
    sms_provider: BaseSMSProvider
    payment_providers: dict[str, BasePaymentProvider]
    smm_provider: BaseSMMProvider | None
    notifications: NotificationService
    workers: list = field(default_factory=list)

    async def shutdown(self) -> None:
        for worker in self.workers:
            await worker.stop()
        await self.sms_provider.close()
        for provider in self.payment_providers.values():
            await provider.close()
        if self.smm_provider is not None:
            await self.smm_provider.close()
        await self.bot.session.close()
        await self.engine.dispose()
        logger.info("app.shutdown_complete")


def build_application(settings: Settings) -> Application:
    """Construct the whole object graph. No I/O beyond opening pools."""
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=settings.parse_mode),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    texts = Texts(settings.locales_path, settings.locale)
    pricing = PricingService(settings)
    sms_provider = build_sms_provider(settings)
    payment_providers = build_payment_providers(settings)
    smm_provider = build_smm_provider(settings)
    catalog = CatalogService(sms_provider, pricing, settings)
    smm_cache = (
        TTLCache(smm_provider.get_services, settings.cache_ttl_seconds)
        if smm_provider is not None
        else None
    )
    notifications = NotificationService(bot, session_factory, settings.admin_ids)

    # Injected into every handler as keyword arguments.
    dispatcher.workflow_data.update(
        settings=settings,
        texts=texts,
        pricing=pricing,
        catalog=catalog,
        engine=engine,
        session_factory=session_factory,
        sms_provider=sms_provider,
        payment_providers=payment_providers,
        smm_provider=smm_provider,
        smm_cache=smm_cache,
        notifications=notifications,
        tokens=TokenStore(),
    )

    _register_middlewares(dispatcher, settings, session_factory)
    dispatcher.include_router(build_router())

    application = Application(
        settings=settings,
        bot=bot,
        dispatcher=dispatcher,
        engine=engine,
        session_factory=session_factory,
        texts=texts,
        sms_provider=sms_provider,
        payment_providers=payment_providers,
        smm_provider=smm_provider,
        notifications=notifications,
    )
    application.workers = _build_workers(application, texts)
    return application


def _register_middlewares(
    dispatcher: Dispatcher, settings: Settings, session_factory: async_sessionmaker
) -> None:
    """Register on both message and callback pipelines, outermost first."""
    layers = [
        ErrorMiddleware(settings),
        DatabaseMiddleware(session_factory),
        UserMiddleware(settings),
        ThrottleMiddleware(settings.rate_limit_per_second),
        MaintenanceMiddleware(settings),
    ]
    for layer in layers:
        dispatcher.message.middleware(layer)
        dispatcher.callback_query.middleware(layer)
    # Pre-checkout must not be throttled: Telegram allows ten seconds to answer.
    dispatcher.pre_checkout_query.middleware(ErrorMiddleware(settings))


def _build_workers(app: Application, texts: Texts) -> list:
    """Create the background loops. They are started by :func:`run`."""
    settings = app.settings
    render = _make_renderer(texts, settings)

    workers = [
        SmsWorker(app.session_factory, app.sms_provider, app.notifications, settings, render),
        PaymentWorker(
            app.session_factory, app.payment_providers, app.notifications, settings, render
        ),
        HealthWorker(app.sms_provider, app.notifications, settings, app.bot),
    ]
    if app.smm_provider is not None:
        workers.append(
            SmmWorker(app.session_factory, app.smm_provider, app.notifications, settings, render)
        )
    return workers


def _make_renderer(texts: Texts, settings: Settings):
    """Adapt the locale renderer for workers, which have no update context."""
    from app.core.constants import OrderStatus
    from app.core.money import format_money
    from app.utils.formatting import order_icon

    def render(key: str, **values) -> str:
        order = values.pop("order", None)
        message = values.pop("message", None)
        if order is not None:
            values.setdefault("order_id", order.id)
            values.setdefault("service", order.service_name)
            values.setdefault("phone", order.phone or "—")
            values.setdefault("quantity", order.quantity or 0)
            values.setdefault("price", format_money(order.price, settings.currency_symbol))
            values.setdefault("status", OrderStatus(order.status).value.title())
            values.setdefault("status_icon", order_icon(order.status))
        if message is not None:
            values.setdefault("sender", message.sender)
            values.setdefault("text", message.text)
        for key_name in ("amount", "balance"):
            if key_name in values and isinstance(values[key_name], int):
                values[key_name] = format_money(values[key_name], settings.currency_symbol)
        return texts.get(key, **values)

    return render
