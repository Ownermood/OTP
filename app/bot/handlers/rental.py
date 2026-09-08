"""The rent-a-number flow: country → duration → confirm."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards
from app.bot.callbacks import Nav, RentalCB
from app.bot.handlers.common import build_context, show, toast
from app.bot.states import RentalStates
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.utils.formatting import format_duration
from app.utils.pagination import paginate
from app.utils.validators import parse_positive_int

router = Router(name="rental")
logger = get_logger(__name__)

#: Rentals are quoted against the provider's generic "any service" code.
RENTAL_SERVICE_CODE = "full"


@router.callback_query(Nav.filter(F.to == "rent"))
async def open_rental(query: CallbackQuery, callback_data: Nav, state: FSMContext, **data):
    context = build_context(data)
    if not context.settings.rental_enabled:
        await toast(query, context.text("errors.invalid_input"), alert=True)
        return

    await state.clear()
    # The service/country pickers are shared with the buy flow; this flag is
    # what tells the country handler to offer durations instead of a quote.
    await state.update_data(mode="rental")
    services = await context.catalog.services()
    await show(
        query,
        context.text("buy.select_service"),
        keyboards.services(
            context.texts, context.locale, paginate(services, callback_data.page), show_search=True
        ),
    )


@router.callback_query(RentalCB.filter(F.hours > 0))
async def confirm_rental(query: CallbackQuery, callback_data: RentalCB, **data):
    """Quote a preset duration."""
    context = build_context(data)
    payload = context.tokens.peek(callback_data.token, query.from_user.id)
    if payload is None:
        await toast(query, context.text("errors.expired_action"), alert=True)
        return
    await _show_quote(query, context, payload, callback_data.hours)


@router.callback_query(RentalCB.filter(F.hours == 0))
async def prompt_custom_hours(query: CallbackQuery, callback_data: RentalCB, state: FSMContext, **data):
    context = build_context(data)
    await state.set_state(RentalStates.entering_hours)
    await state.update_data(rental_token=callback_data.token)
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
    token = (await state.get_data()).get("rental_token")
    payload = context.tokens.peek(token, message.from_user.id) if token else None
    if payload is None:
        await state.clear()
        raise ValidationError("rental quote expired")

    await state.clear()
    await _show_quote(message, context, payload, hours)


async def _show_quote(event, context, payload: dict, hours: int) -> None:
    """Price a rental and mint the single-use confirm token."""
    # Rental price scales with duration; the daily rate is the hourly base.
    price = payload["price"] * max(1, hours // 24 or 1)
    token = context.tokens.issue(
        event.from_user.id,
        kind="rental",
        service_code=payload["service_code"],
        service_name=payload["service_name"],
        country_id=payload["country_id"],
        country_name=payload["country_name"],
        hours=hours,
        price=price,
    )
    balance = context.user.balance
    await show(
        event,
        context.text(
            "rental.confirm",
            service=payload["service_name"],
            country=payload["country_name"],
            duration=format_duration(hours),
            price=context.money(price),
            balance=context.money(balance),
            balance_after=context.money(max(balance - price, 0)),
        ),
        keyboards.purchase_confirm(context.texts, context.locale, token),
    )


async def do_rental_purchase(query: CallbackQuery, payload: dict, context) -> None:
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
