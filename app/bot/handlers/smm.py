"""SMM panel.

Platform → service → link → quantity → price → confirm → order → track.

Same money discipline as the SMS flow: the quote lives in a server-side token,
the confirm button consumes it once, and the price is re-derived from the live
catalogue inside the service before the wallet is touched.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards
from app.bot.callbacks import ConfirmCB, Nav, SmmCB
from app.bot.handlers.common import Context, build_context, show, toast
from app.bot.listing import paginate_lines, smm_service_lines
from app.bot.states import SmmStates
from app.core.constants import OrderStatus
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.utils.formatting import order_icon, truncate
from app.utils.pagination import paginate
from app.utils.validators import clean_search_query, parse_link, parse_positive_int

router = Router(name="smm")
logger = get_logger(__name__)


@router.callback_query(Nav.filter(F.to == "smm"))
async def open_panel(query: CallbackQuery, state: FSMContext, **data):
    await state.clear()
    context = build_context(data)
    if not context.smm.enabled:
        await show(
            query, context.text("smm.disabled"), keyboards.back_home(context.texts, context.locale)
        )
        return

    categories = await context.smm.categories()
    await show(
        query,
        context.text("smm.main"),
        keyboards.smm_categories(context.texts, context.locale, categories),
    )


@router.callback_query(SmmCB.filter(F.action == "category"))
async def open_category(query: CallbackQuery, callback_data: SmmCB, **data):
    context = build_context(data)
    services = await context.smm.services_in(callback_data.value)
    if not services:
        await toast(query, context.text("common.empty"), alert=True)
        return

    page = paginate(services, callback_data.page, per_page=10)
    await show(
        query,
        context.text("smm.select_service", platform=callback_data.value.title()),
        keyboards.smm_services(
            context.texts, context.locale, page, callback_data.value, context.settings.currency_symbol
        ),
    )


@router.callback_query(SmmCB.filter(F.action == "show_all"))
async def show_all_smm(query: CallbackQuery, **data):
    """Every SMM service with its rate, across all platforms."""
    context = build_context(data)
    services = await context.smm.services()
    parts = paginate_lines(
        smm_service_lines(services, context.settings.currency_symbol),
        context.text("smm.all_services", count=len(services)),
    )
    if not parts:
        await toast(query, context.text("common.empty"), alert=True)
        return

    await query.answer()
    keyboard = keyboards.back_home(context.texts, context.locale, back_to="smm")
    for part in parts:
        await query.message.answer(
            part.body, reply_markup=keyboard if part.part == part.total else None
        )


@router.callback_query(SmmCB.filter(F.action == "search"))
async def prompt_search(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    await state.set_state(SmmStates.searching)
    await show(
        query,
        context.text("buy.search_service_prompt"),
        keyboards.back_home(context.texts, context.locale, back_to="smm"),
    )


@router.message(SmmStates.searching)
async def search_services(message: Message, state: FSMContext, **data):
    context = build_context(data)
    query_text = clean_search_query(message.text or "")
    matches = await context.smm.search(query_text)
    await state.clear()

    if not matches:
        await show(
            message,
            context.text("buy.search_empty", query=query_text),
            keyboards.back_home(context.texts, context.locale, back_to="smm"),
        )
        return

    page = paginate(matches, 1, per_page=10)
    await show(
        message,
        context.text("buy.search_results", query=query_text, count=len(matches)),
        keyboards.smm_services(
            context.texts,
            context.locale,
            page,
            # Search spans every platform, so paging and Back belong to the
            # panel root rather than to any one category.
            category=None,
            currency=context.settings.currency_symbol,
        ),
    )


@router.callback_query(SmmCB.filter(F.action == "service"))
async def prompt_link(query: CallbackQuery, callback_data: SmmCB, state: FSMContext, **data):
    context = build_context(data)
    service = await context.smm.find_service(callback_data.value)
    if service is None:
        await toast(query, context.text("errors.expired_action"), alert=True)
        return

    await state.set_state(SmmStates.entering_link)
    await state.update_data(smm_service_id=service.service_id)
    await show(
        query,
        context.text(
            "smm.service_detail",
            service=service.name,
            rate=context.money(service.rate_per_1000),
            minimum=service.min_quantity,
            maximum=service.max_quantity,
        ),
        keyboards.back_home(context.texts, context.locale, back_to="smm"),
    )


@router.message(SmmStates.entering_link)
async def enter_link(message: Message, state: FSMContext, **data):
    context = build_context(data)
    link = parse_link(message.text or "")
    service = await _stored_service(context, state)

    await state.set_state(SmmStates.entering_quantity)
    await state.update_data(smm_link=link)
    await show(
        message,
        context.text(
            "smm.enter_quantity",
            service=service.name,
            link=truncate(link, 60),
            minimum=service.min_quantity,
            maximum=service.max_quantity,
        ),
        keyboards.back_home(context.texts, context.locale, back_to="smm"),
    )


@router.message(SmmStates.entering_quantity)
async def enter_quantity(message: Message, state: FSMContext, **data):
    """Quote the order and mint the single-use confirm token."""
    context = build_context(data)
    service = await _stored_service(context, state)
    stored = await state.get_data()
    link = stored.get("smm_link", "")

    quantity = parse_positive_int(
        message.text or "", minimum=service.min_quantity, maximum=service.max_quantity
    )
    breakdown = context.smm.quote(service, quantity)
    await state.clear()

    token = context.tokens.issue(
        message.from_user.id,
        kind="smm",
        service_id=service.service_id,
        service_name=service.name,
        link=link,
        quantity=quantity,
        price=breakdown.total,
    )
    balance = context.user.balance
    await show(
        message,
        context.text(
            "smm.confirm",
            service=service.name,
            link=truncate(link, 60),
            quantity=quantity,
            price=context.money(breakdown.total),
            balance=context.money(balance),
            balance_after=context.money(max(balance - breakdown.total, 0)),
        ),
        keyboards.confirm_or_cancel(
            context.texts, context.locale, ConfirmCB(token=token).pack(), "smm"
        ),
    )


async def do_smm_purchase(query: CallbackQuery, payload: dict, context: Context) -> None:
    """Called by the shared confirm handler when the token is an SMM quote."""
    purchase = await context.smm.create_order(
        user_id=query.from_user.id,
        service_id=payload["service_id"],
        link=payload["link"],
        quantity=payload["quantity"],
        quoted_price=payload["price"],
    )
    order = purchase.order
    await show(
        query,
        context.text(
            "smm.created",
            order_id=order.id,
            service=order.service_name,
            quantity=order.quantity,
            price=context.money(order.price),
        ),
        keyboards.smm_order(context.texts, context.locale, order.id),
    )


@router.callback_query(SmmCB.filter(F.action == "track"))
async def track_order(query: CallbackQuery, callback_data: SmmCB, **data):
    context = build_context(data)
    order = await context.smm.get_owned(int(callback_data.value), query.from_user.id)
    order = await context.smm.refresh_status(order)

    await show(
        query,
        context.text(
            "smm.status",
            order_id=order.id,
            status_icon=order_icon(order.status),
            status=OrderStatus(order.status).value.title(),
            quantity=order.quantity,
            start_count=order.start_count if order.start_count is not None else "—",
            remains=order.remains if order.remains is not None else "—",
        ),
        keyboards.smm_order(context.texts, context.locale, order.id),
    )


async def _stored_service(context: Context, state: FSMContext):
    """Re-resolve the in-progress service, failing cleanly if the panel dropped it."""
    service_id = (await state.get_data()).get("smm_service_id")
    service = await context.smm.find_service(service_id) if service_id else None
    if service is None:
        await state.clear()
        raise ValidationError("service is no longer offered")
    return service
