"""The rent-a-number flow: country → duration → service → confirm.

The order matters. The provider prices a rental for a whole (country,
duration) pair rather than per hour, so the duration is chosen *before* any
price can be shown. Once a service is picked, its real cost goes into a
single-use token exactly as in the buy flow.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards
from app.bot.callbacks import Nav, RentCB
from app.bot.handlers.common import Context, build_context, show, toast
from app.bot.states import RentalStates
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.utils.formatting import format_duration
from app.utils.pagination import paginate
from app.utils.validators import clean_search_query, parse_positive_int

router = Router(name="rental")
logger = get_logger(__name__)


def _require_enabled(context: Context) -> None:
    if not context.settings.rental_enabled:
        raise ValidationError("rentals are disabled")


# -- country ---------------------------------------------------------------


@router.callback_query(Nav.filter(F.to == "rent"))
async def open_rental(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    _require_enabled(context)
    await state.clear()
    await _render_countries(query, context, page=1)


@router.callback_query(RentCB.filter(F.action == "list"))
async def paginate_countries(query: CallbackQuery, callback_data: RentCB, **data):
    context = build_context(data)
    _require_enabled(context)
    await _render_countries(query, context, page=callback_data.page)


@router.callback_query(RentCB.filter(F.action == "search"))
async def prompt_country_search(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    await state.set_state(RentalStates.searching_country)
    await show(
        query,
        context.text("buy.search_country_prompt"),
        keyboards.back_home(context.texts, context.locale, back_to="rent"),
    )


@router.message(RentalStates.searching_country)
async def search_countries(message: Message, state: FSMContext, **data):
    context = build_context(data)
    query_text = clean_search_query(message.text or "")
    matches = await context.catalog.search_rental_countries(query_text)
    await state.clear()

    if not matches:
        await show(
            message,
            context.text("buy.search_empty", query=query_text),
            keyboards.back_home(context.texts, context.locale, back_to="rent"),
        )
        return

    await show(
        message,
        context.text("buy.search_results", query=query_text, count=len(matches)),
        keyboards.rental_countries(context.texts, context.locale, paginate(matches, 1)),
    )


# -- duration --------------------------------------------------------------


@router.callback_query(RentCB.filter(F.action == "country"))
async def choose_duration(query: CallbackQuery, callback_data: RentCB, **data):
    context = build_context(data)
    _require_enabled(context)

    country_id = int(callback_data.value)
    country = await context.catalog.find_rental_country(country_id)
    await show(
        query,
        context.text(
            "rental.select_duration",
            country=country.name if country else country_id,
            service="—",
        ),
        keyboards.rental_durations(
            context.texts,
            context.locale,
            country_id,
            context.settings.min_rental_hours,
            context.settings.max_rental_hours,
        ),
    )


@router.callback_query(RentCB.filter(F.action == "custom"))
async def prompt_custom_hours(query: CallbackQuery, callback_data: RentCB, state: FSMContext, **data):
    context = build_context(data)
    await state.set_state(RentalStates.entering_hours)
    await state.update_data(rental_country=int(callback_data.value))
    await show(
        query,
        context.text(
            "rental.custom_prompt",
            minimum=context.settings.min_rental_hours,
            maximum=context.settings.max_rental_hours,
        ),
        keyboards.back_home(context.texts, context.locale, back_to="rent"),
    )


@router.message(RentalStates.entering_hours)
async def enter_custom_hours(message: Message, state: FSMContext, **data):
    context = build_context(data)
    hours = parse_positive_int(
        message.text or "",
        minimum=context.settings.min_rental_hours,
        maximum=context.settings.max_rental_hours,
    )
    country_id = (await state.get_data()).get("rental_country")
    await state.clear()
    if country_id is None:
        raise ValidationError("rental selection expired")

    await _render_services(message, context, int(country_id), hours, page=1)


# -- service and quote -----------------------------------------------------


@router.callback_query(RentCB.filter(F.action == "hours"))
async def list_services(query: CallbackQuery, callback_data: RentCB, **data):
    context = build_context(data)
    _require_enabled(context)

    raw_country, _, raw_hours = callback_data.value.partition("_")
    await _render_services(
        query, context, int(raw_country), int(raw_hours), page=callback_data.page
    )


@router.callback_query(RentCB.filter(F.action == "quote"))
async def confirm_rental(query: CallbackQuery, callback_data: RentCB, **data):
    """Show the rental quote. Peeking does not consume the token."""
    context = build_context(data)
    payload = context.tokens.peek(callback_data.value, query.from_user.id)
    if payload is None:
        await toast(query, context.text("errors.expired_action"), alert=True)
        return

    balance = context.user.balance
    price = payload["price"]
    await show(
        query,
        context.text(
            "rental.confirm",
            service=payload["service_name"],
            country=payload["country_name"],
            duration=format_duration(payload["hours"]),
            price=context.money(price),
            balance=context.money(balance),
            balance_after=context.money(max(balance - price, 0)),
        ),
        keyboards.purchase_confirm(context.texts, context.locale, callback_data.value),
    )


async def do_rental_purchase(query: CallbackQuery, payload: dict, context: Context) -> None:
    """Called by the shared confirm handler when the token is a rental quote."""
    result = await context.orders.purchase_rental(
        user_id=query.from_user.id,
        service_code=payload["service_code"],
        service_name=payload["service_name"],
        country_id=payload["country_id"],
        country_name=payload["country_name"],
        hours=payload["hours"],
        quoted_price=payload["price"],
    )
    order = result.order
    await show(
        query,
        context.text(
            "rental.created",
            phone=order.phone,
            duration=format_duration(payload["hours"]),
            order_id=order.id,
        ),
        keyboards.activation(context.texts, context.locale, order.id),
    )


# -- rendering -------------------------------------------------------------


async def _render_countries(event, context: Context, page: int) -> None:
    countries = await context.catalog.rental_countries()
    await show(
        event,
        context.text("buy.select_country", service="Rental"),
        keyboards.rental_countries(context.texts, context.locale, paginate(countries, page)),
    )


async def _render_services(event, context: Context, country_id: int, hours: int, page: int) -> None:
    """List rentable services at their real cost for this country and duration."""
    country = await context.catalog.find_rental_country(country_id)
    country_name = country.name if country else str(country_id)
    offers = await context.catalog.rental_services(country_id, hours)

    if not offers:
        await show(
            event,
            context.text("errors.no_numbers"),
            keyboards.back_home(context.texts, context.locale, back_to="rent"),
        )
        return

    paged = paginate(offers, page)
    tokens = {
        priced.offer.code: context.tokens.issue(
            event.from_user.id,
            kind="rental",
            service_code=priced.offer.code,
            service_name=priced.offer.name,
            country_id=country_id,
            country_name=country_name,
            hours=hours,
            price=priced.price,
        )
        for priced in paged.items
    }
    await show(
        event,
        context.text("rental.select_service", country=country_name, duration=format_duration(hours)),
        keyboards.rental_services(
            context.texts,
            context.locale,
            paged,
            tokens,
            country_id,
            hours,
            context.settings.currency_symbol,
        ),
    )
