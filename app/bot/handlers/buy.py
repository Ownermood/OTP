"""The buy-a-number flow.

Service → country → confirm → purchase, with search at both list steps.

The safety-critical part is what a callback carries. A country button holds an
opaque token; the service code, country id and quoted price behind it live in
the server-side token store. The confirm button consumes that token exactly
once, so a double tap cannot buy twice, and the price is re-read from the
provider before the wallet is touched regardless.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards
from app.bot.callbacks import ConfirmCB, CountryCB, FavoriteCB, Nav, ServiceCB
from app.bot.handlers.common import Context, build_context, show, toast
from app.bot.listing import country_lines, paginate_lines, service_lines
from app.bot.states import BuyStates
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.utils.pagination import paginate
from app.utils.validators import clean_search_query

router = Router(name="buy")
logger = get_logger(__name__)


# -- service selection ------------------------------------------------------


@router.callback_query(Nav.filter(F.to == "buy"))
async def open_services(query: CallbackQuery, callback_data: Nav, state: FSMContext, **data):
    await state.clear()
    context = build_context(data)
    await _render_services(query, context, page=callback_data.page)


@router.callback_query(Nav.filter(F.to == "services_all"))
async def show_all_services(query: CallbackQuery, **data):
    """Dump the whole service catalogue as text.

    The button grid is for picking; this is for seeing what exists without
    tapping through pages of it.
    """
    context = build_context(data)
    services = await context.catalog.services()
    await _send_listing(
        query,
        context,
        service_lines(services),
        header=context.text("buy.all_services", count=len(services)),
        back_to="buy",
    )


@router.callback_query(Nav.filter(F.to == "countries_all"))
async def show_all_countries(query: CallbackQuery, state: FSMContext, **data):
    """Every country for the chosen service, with price and stock."""
    context = build_context(data)
    service_code = (await state.get_data()).get("service_code")
    if not service_code:
        await _render_services(query, context)
        return

    service = await context.catalog.find_service(service_code)
    countries = await context.catalog.countries(service_code)
    await _send_listing(
        query,
        context,
        country_lines(countries, context.settings.currency_symbol),
        header=context.text(
            "buy.all_countries",
            service=service.name if service else service_code,
            count=len(countries),
        ),
        back_to="countries",
    )


async def _send_listing(query, context, lines, header: str, back_to: str) -> None:
    """Send a listing as however many messages it needs.

    Only the last one carries the keyboard, so the user is not left scrolling
    past several identical button rows to find the live one.
    """
    parts = paginate_lines(lines, header)
    if not parts:
        await toast(query, context.text("common.empty"), alert=True)
        return

    await query.answer()
    keyboard = keyboards.back_home(context.texts, context.locale, back_to=back_to)
    for part in parts:
        await query.message.answer(
            part.body, reply_markup=keyboard if part.part == part.total else None
        )


@router.callback_query(Nav.filter(F.to == "buy_search"))
async def prompt_service_search(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    await state.set_state(BuyStates.searching_service)
    await show(
        query,
        context.text("buy.search_service_prompt"),
        keyboards.back_home(context.texts, context.locale, back_to="buy"),
    )


@router.message(BuyStates.searching_service)
async def search_services(message: Message, state: FSMContext, **data):
    context = build_context(data)
    query_text = clean_search_query(message.text or "")
    matches = await context.catalog.search_services(query_text)
    await state.clear()

    if not matches:
        await show(
            message,
            context.text("buy.search_empty", query=query_text),
            keyboards.back_home(context.texts, context.locale, back_to="buy"),
        )
        return

    page = paginate(matches, 1)
    await show(
        message,
        context.text("buy.search_results", query=query_text, count=len(matches)),
        keyboards.services(context.texts, context.locale, page, show_search=False),
    )


# -- country selection ------------------------------------------------------


@router.callback_query(ServiceCB.filter())
async def open_countries(
    query: CallbackQuery, callback_data: ServiceCB, state: FSMContext, **data
):
    context = build_context(data)
    await state.update_data(service_code=callback_data.code)
    await _render_countries(query, context, callback_data.code, callback_data.page)


@router.callback_query(Nav.filter(F.to == "countries"))
async def paginate_countries(
    query: CallbackQuery, callback_data: Nav, state: FSMContext, **data
):
    context = build_context(data)
    service_code = (await state.get_data()).get("service_code")
    if not service_code:
        await _render_services(query, context)
        return
    await _render_countries(query, context, service_code, callback_data.page)


@router.callback_query(Nav.filter(F.to == "country_search"))
async def prompt_country_search(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    await state.set_state(BuyStates.searching_country)
    await show(
        query,
        context.text("buy.search_country_prompt"),
        keyboards.back_home(context.texts, context.locale, back_to="buy"),
    )


@router.message(BuyStates.searching_country)
async def search_countries(message: Message, state: FSMContext, **data):
    context = build_context(data)
    stored = await state.get_data()
    service_code = stored.get("service_code")
    if not service_code:
        await state.clear()
        await _render_services(message, context)
        return

    query_text = clean_search_query(message.text or "")
    matches = await context.catalog.search_countries(service_code, query_text)
    await state.set_state(None)
    await state.update_data(service_code=service_code)

    if not matches:
        await show(
            message,
            context.text("buy.search_empty", query=query_text),
            keyboards.back_home(context.texts, context.locale, back_to="buy"),
        )
        return

    service = await context.catalog.find_service(service_code)
    page = paginate(matches, 1)
    tokens = _issue_tokens(context, message.from_user.id, service_code, service, page.items)
    await show(
        message,
        context.text("buy.search_results", query=query_text, count=len(matches)),
        keyboards.countries(
            context.texts, context.locale, page, tokens, context.settings.currency_symbol
        ),
    )


# -- confirmation and purchase ---------------------------------------------


@router.callback_query(CountryCB.filter())
async def confirm_purchase(
    query: CallbackQuery, callback_data: CountryCB, state: FSMContext, **data
):
    """Show the quote. Peeking does not consume the token -- confirming does."""
    context = build_context(data)
    payload = context.tokens.peek(callback_data.token, query.from_user.id)
    if payload is None:
        await toast(query, context.text("errors.expired_action"), alert=True)
        await _render_services(query, context)
        return

    await state.update_data(quote_token=callback_data.token)

    balance = context.user.balance
    price = payload["price"]
    await show(
        query,
        context.text(
            "buy.confirm",
            service=payload["service_name"],
            country=payload["country_name"],
            price=context.money(price),
            balance=context.money(balance),
            balance_after=context.money(max(balance - price, 0)),
        ),
        keyboards.purchase_confirm(context.texts, context.locale, callback_data.token),
    )


@router.callback_query(ConfirmCB.filter())
async def do_purchase(query: CallbackQuery, callback_data: ConfirmCB, state: FSMContext, **data):
    """Buy the number. The token is consumed first, so a double tap is inert."""
    context = build_context(data)
    payload = context.tokens.consume(callback_data.token, query.from_user.id)
    if payload is None:
        await toast(query, context.text("errors.duplicate_operation"), alert=True)
        return

    if payload.get("kind") == "smm":
        from app.bot.handlers.smm import do_smm_purchase

        await state.clear()
        await do_smm_purchase(query, payload, context)
        return

    await state.clear()
    result = await context.orders.purchase_activation(
        user_id=query.from_user.id,
        service_code=payload["service_code"],
        service_name=payload["service_name"],
        country_id=payload["country_id"],
        country_name=payload["country_name"],
        quoted_price=payload["price"],
    )
    order = result.order
    await show(
        query,
        context.text(
            "buy.purchased",
            phone=order.phone,
            country=order.country_name,
            service=order.service_name,
            price=context.money(order.price),
            order_id=order.id,
        ),
        keyboards.activation(context.texts, context.locale, order.id),
    )


@router.callback_query(FavoriteCB.filter(F.action == "add_token"))
async def add_favorite_from_quote(query: CallbackQuery, state: FSMContext, **data):
    """Save the combination currently being quoted."""
    context = build_context(data)
    token = (await state.get_data()).get("quote_token")
    payload = context.tokens.peek(token, query.from_user.id) if token else None
    if payload is None:
        await toast(query, context.text("errors.expired_action"), alert=True)
        return

    added = await context.users.add_favorite(
        query.from_user.id,
        payload["service_code"],
        payload["service_name"],
        payload["country_id"],
        payload["country_name"],
    )
    await toast(query, context.text("favorites.added" if added else "favorites.exists"))


# -- rendering helpers ------------------------------------------------------


async def _render_services(event, context: Context, page: int = 1) -> None:
    services = await context.catalog.services()
    recent = await context.orders.recently_used(context.user.id) if page == 1 else ()
    await show(
        event,
        context.text("buy.select_service"),
        keyboards.services(context.texts, context.locale, paginate(services, page), recent),
    )


async def _render_countries(event, context: Context, service_code: str, page: int) -> None:
    service = await context.catalog.find_service(service_code)
    if service is None:
        raise ValidationError("unknown service")

    countries = await context.catalog.countries(service_code)
    paged = paginate(countries, page)
    tokens = _issue_tokens(context, event.from_user.id, service_code, service, paged.items)
    await show(
        event,
        context.text("buy.select_country", service=service.name),
        keyboards.countries(
            context.texts, context.locale, paged, tokens, context.settings.currency_symbol
        ),
    )


def _issue_tokens(context: Context, user_id: int, service_code: str, service, items):
    """Mint one single-use token per visible country button."""
    return {
        priced.country.id: context.tokens.issue(
            user_id,
            service_code=service_code,
            service_name=service.name if service else service_code,
            country_id=priced.country.id,
            country_name=priced.country.name,
            price=priced.price,
        )
        for priced in items
    }
