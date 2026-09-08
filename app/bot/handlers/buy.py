"""The buy-a-number flow.

Country → service → confirm → purchase, with search at both list steps.

Country comes first because that is the question a buyer has, and because
providers price per country: a service list with no country chosen is
thousands of opaque codes with no prices against them.

The safety-critical part is what a callback carries. A country button holds
only a country id, which grants nothing. A service button holds an opaque
token; the service code, country id and quoted price behind it live in the
server-side token store. The confirm button consumes that token exactly once,
so a double tap cannot buy twice, and the price is re-read from the provider
before the wallet is touched regardless.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards
from app.bot.callbacks import ConfirmCB, CountryCB, FavoriteCB, Nav, QuoteCB
from app.bot.handlers.common import Context, build_context, show, toast
from app.bot.listing import country_lines, offer_lines, paginate_lines
from app.bot.states import BuyStates
from app.core.logging import get_logger
from app.utils.pagination import paginate
from app.utils.validators import clean_search_query

router = Router(name="buy")
logger = get_logger(__name__)


# -- country selection (the opening screen) ---------------------------------


@router.callback_query(Nav.filter(F.to == "buy"))
async def open_countries(query: CallbackQuery, callback_data: Nav, state: FSMContext, **data):
    await state.clear()
    context = build_context(data)
    await _render_countries(query, context, page=callback_data.page)


@router.callback_query(Nav.filter(F.to == "countries_all"))
async def show_all_countries(query: CallbackQuery, **data):
    """Dump every country as text.

    The button grid is for picking; this is for seeing what exists without
    tapping through pages of it.
    """
    context = build_context(data)
    countries = await context.catalog.all_countries()
    await _send_listing(
        query,
        context,
        country_lines(countries, context.settings.currency_symbol),
        header=context.text("buy.all_countries", count=len(countries)),
        back_to="buy",
    )


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
    query_text = clean_search_query(message.text or "")
    matches = await context.catalog.search_all_countries(query_text)
    await state.clear()

    if not matches:
        await show(
            message,
            context.text("buy.search_empty", query=query_text),
            keyboards.back_home(context.texts, context.locale, back_to="buy"),
        )
        return

    await show(
        message,
        context.text("buy.search_results", query=query_text, count=len(matches)),
        keyboards.country_grid(
            context.texts, context.locale, paginate(matches, 1), context.settings.currency_symbol
        ),
    )


# -- service selection, within the chosen country ---------------------------


@router.callback_query(CountryCB.filter())
async def open_services(query: CallbackQuery, callback_data: CountryCB, state: FSMContext, **data):
    context = build_context(data)
    await state.update_data(country_id=callback_data.id)
    await _render_services(query, context, callback_data.id, callback_data.page)


@router.callback_query(Nav.filter(F.to == "country"))
async def paginate_services(query: CallbackQuery, callback_data: Nav, state: FSMContext, **data):
    context = build_context(data)
    country_id = (await state.get_data()).get("country_id")
    if country_id is None:
        await _render_countries(query, context)
        return
    await _render_services(query, context, country_id, callback_data.page)


@router.callback_query(Nav.filter(F.to == "services_all"))
async def show_all_services(query: CallbackQuery, state: FSMContext, **data):
    """Every service available in the chosen country, with price and stock."""
    context = build_context(data)
    country_id = (await state.get_data()).get("country_id")
    if country_id is None:
        await _render_countries(query, context)
        return

    country = await context.catalog.find_any_country(country_id)
    offers = await context.catalog.offers_in(country_id)
    await _send_listing(
        query,
        context,
        offer_lines(offers, context.settings.currency_symbol),
        header=context.text(
            "buy.all_services",
            country=country.country.name if country else country_id,
            count=len(offers),
        ),
        back_to="country",
    )


@router.callback_query(Nav.filter(F.to == "buy_search"))
async def prompt_service_search(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    if (await state.get_data()).get("country_id") is None:
        await _render_countries(query, build_context(data))
        return
    await state.set_state(BuyStates.searching_service)
    await show(
        query,
        context.text("buy.search_service_prompt"),
        keyboards.back_home(context.texts, context.locale, back_to="country"),
    )


@router.message(BuyStates.searching_service)
async def search_services(message: Message, state: FSMContext, **data):
    context = build_context(data)
    stored = await state.get_data()
    country_id = stored.get("country_id")
    if country_id is None:
        await state.clear()
        await _render_countries(message, context)
        return

    query_text = clean_search_query(message.text or "")
    matches = await context.catalog.search_offers(country_id, query_text)
    await state.set_state(None)
    await state.update_data(country_id=country_id)

    if not matches:
        await show(
            message,
            context.text("buy.search_empty", query=query_text),
            keyboards.back_home(context.texts, context.locale, back_to="country"),
        )
        return

    country = await context.catalog.find_any_country(country_id)
    page = paginate(matches, 1)
    tokens = _issue_tokens(context, message.from_user.id, country, page.items)
    await show(
        message,
        context.text("buy.search_results", query=query_text, count=len(matches)),
        keyboards.country_services(
            context.texts, context.locale, page, tokens, context.settings.currency_symbol
        ),
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


# -- confirmation and purchase ---------------------------------------------


@router.callback_query(QuoteCB.filter())
async def confirm_purchase(
    query: CallbackQuery, callback_data: QuoteCB, state: FSMContext, **data
):
    """Show the quote. Peeking does not consume the token -- confirming does."""
    context = build_context(data)
    payload = context.tokens.peek(callback_data.token, query.from_user.id)
    if payload is None:
        await toast(query, context.text("errors.expired_action"), alert=True)
        await _render_countries(query, context)
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


async def _render_countries(event, context: Context, page: int = 1) -> None:
    countries = await context.catalog.all_countries()
    recent, recent_tokens = await _recent_pairs(context, event.from_user.id, page)
    await show(
        event,
        context.text("buy.select_country", count=len(countries)),
        keyboards.country_grid(
            context.texts,
            context.locale,
            paginate(countries, page),
            context.settings.currency_symbol,
            recent,
            recent_tokens,
        ),
    )


async def _recent_pairs(context: Context, user_id: int, page: int):
    """Recently bought service/country pairs, quoted at today's price.

    Only on the first page, and only for pairs still on sale -- a shortcut that
    leads to "unavailable" is worse than no shortcut.
    """
    if page != 1:
        return (), {}

    recent = await context.orders.recently_used(context.user.id)
    tokens: dict[str, str] = {}
    usable = []
    for order in recent:
        offer = await context.catalog.find_offer(order.country_id, order.service_code)
        if offer is None:
            continue
        usable.append(order)
        tokens[f"{order.service_code}@{order.country_id}"] = context.tokens.issue(
            user_id,
            service_code=order.service_code,
            service_name=offer.offer.service.name,
            country_id=order.country_id,
            country_name=order.country_name,
            price=offer.price,
        )
    return usable, tokens


async def _render_services(event, context: Context, country_id: int, page: int = 1) -> None:
    country = await context.catalog.find_any_country(country_id)
    offers = await context.catalog.offers_in(country_id)
    if not offers:
        await toast(event, context.text("common.empty"), alert=True)
        await _render_countries(event, context)
        return

    paged = paginate(offers, page)
    tokens = _issue_tokens(context, event.from_user.id, country, paged.items)
    name = country.country.name if country else str(country_id)
    await show(
        event,
        context.text("buy.select_service", country=name, count=len(offers)),
        keyboards.country_services(
            context.texts, context.locale, paged, tokens, context.settings.currency_symbol
        ),
    )


def _issue_tokens(context: Context, user_id: int, country, items):
    """Mint one single-use token per visible service button."""
    country_id = country.country.id if country else 0
    country_name = country.country.name if country else str(country_id)
    return {
        priced.offer.service.code: context.tokens.issue(
            user_id,
            service_code=priced.offer.service.code,
            service_name=priced.offer.service.name,
            country_id=country_id,
            country_name=country_name,
            price=priced.price,
        )
        for priced in items
    }
