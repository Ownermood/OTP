"""TG-Lion Telegram numbers: country -> buy -> Get OTP -> Refresh/Cancel.

Its own router, its own screens -- see app/providers/tg_lion.py and
app/services/telegram_numbers.py for why this is not folded into the
existing SMS-activation buy flow (no service dimension, no provider-side
cancel). Money discipline matches every other purchase in the bot: the
price shown here is never trusted at charge time -- ``purchase()`` always
re-reads it live before touching the wallet.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards
from app.bot.callbacks import Nav, OrderCB, TgLionCB
from app.bot.handlers.common import Context, build_context, show, toast
from app.bot.states import TgLionStates
from app.core.constants import OrderStatus
from app.core.logging import get_logger
from app.utils.pagination import paginate
from app.utils.validators import clean_search_query

router = Router(name="tg_lion")
logger = get_logger(__name__)


@router.callback_query(Nav.filter(F.to == "telegram"))
async def open_countries(query: CallbackQuery, state: FSMContext, **data):
    await state.clear()
    context = build_context(data)
    await _show_countries(query, context, page=1)


@router.callback_query(TgLionCB.filter(F.action == "page"))
async def paged_countries(query: CallbackQuery, callback_data: TgLionCB, **data):
    context = build_context(data)
    await _show_countries(query, context, page=callback_data.page)


async def _show_countries(query: CallbackQuery, context: Context, page: int) -> None:
    if not context.telegram_numbers.enabled:
        await show(
            query, context.text("telegram.disabled"), keyboards.back_home(context.texts, context.locale)
        )
        return

    countries = await context.telegram_numbers.countries()
    if not countries:
        await toast(query, context.text("common.empty"), alert=True)
        return

    page_slice = paginate(countries, page, per_page=10)
    await show(
        query,
        context.text("telegram.countries"),
        keyboards.tg_lion_countries(
            context.texts, context.locale, page_slice, context.settings.currency_symbol
        ),
    )


@router.callback_query(Nav.filter(F.to == "telegram_search"))
async def prompt_country_search(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    await state.set_state(TgLionStates.searching_country)
    await show(
        query,
        context.text("buy.search_country_prompt"),
        keyboards.back_home(context.texts, context.locale, back_to="telegram"),
    )


@router.message(TgLionStates.searching_country)
async def search_countries(message: Message, state: FSMContext, **data):
    """By name, ISO alpha-2/3, dial code, or TG-Lion's own short code."""
    context = build_context(data)
    query_text = clean_search_query(message.text or "")
    matches = await context.telegram_numbers.search_countries(query_text)
    await state.clear()

    if not matches:
        await show(
            message,
            context.text("buy.search_empty", query=query_text),
            keyboards.back_home(context.texts, context.locale, back_to="telegram"),
        )
        return

    await show(
        message,
        context.text("buy.search_results", query=query_text, count=len(matches)),
        keyboards.tg_lion_countries(
            context.texts, context.locale, paginate(matches, 1), context.settings.currency_symbol
        ),
    )


@router.callback_query(TgLionCB.filter(F.action == "country"))
async def country_detail(query: CallbackQuery, callback_data: TgLionCB, **data):
    context = build_context(data)
    country = await context.telegram_numbers.find_country(callback_data.country or "")
    if country is None:
        await toast(query, context.text("errors.expired_action"), alert=True)
        return

    await show(
        query,
        context.text(
            "telegram.country_detail",
            country=country.name,
            price=context.money(country.cost),
            stock=country.available if country.available is not None else "—",
        ),
        keyboards.tg_lion_confirm(context.texts, context.locale, country.code),
    )


@router.callback_query(TgLionCB.filter(F.action == "buy"))
async def buy_number(query: CallbackQuery, callback_data: TgLionCB, **data):
    """Purchase a number. The price shown on the previous screen is never
    trusted here -- ``purchase()`` re-reads it live before charging."""
    context = build_context(data)
    country_code = callback_data.country or ""

    purchase = await context.telegram_numbers.purchase(
        user_id=query.from_user.id, country_code=country_code, quoted_price=0
    )
    order = purchase.order
    await show(
        query,
        context.text(
            "telegram.purchased",
            phone=order.phone,
            price=context.money(order.price),
        ),
        keyboards.tg_number_purchased(context.texts, context.locale, order.id, order.phone or ""),
    )


@router.callback_query(OrderCB.filter(F.action == "tg_refresh"))
async def refresh_number(query: CallbackQuery, callback_data: OrderCB, **data):
    """Ask TG-Lion for the code right now. Never buys another number."""
    context = build_context(data)
    order = await context.telegram_numbers.get_owned(callback_data.order_id, query.from_user.id)
    order = await context.telegram_numbers.refresh(order)

    if OrderStatus(order.status) == OrderStatus.SUCCESS:
        await show(
            query,
            context.text("telegram.received", phone=order.phone, code=order.sms_code),
            keyboards.tg_number_received(
                context.texts,
                context.locale,
                order.phone or "",
                order.sms_code or "",
                order.link or "",
            ),
        )
        return

    if OrderStatus(order.status).is_final:
        # Expired/cancelled/failed between the tap landing and this running.
        await toast(query, context.text("wallet.manual_already_reviewed"), alert=True)
        return

    await show(
        query,
        context.text("telegram.waiting", phone=order.phone),
        keyboards.tg_number_waiting(context.texts, context.locale, order.id),
    )


@router.callback_query(OrderCB.filter(F.action == "tg_cancel"))
async def cancel_number(query: CallbackQuery, callback_data: OrderCB, **data):
    context = build_context(data)
    order = await context.telegram_numbers.cancel(callback_data.order_id, query.from_user.id)
    await show(
        query,
        context.text("telegram.cancelled", price=context.money(order.price)),
        keyboards.back_home(context.texts, context.locale),
    )
