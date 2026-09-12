"""Order history, order detail, refresh and cancellation."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot import keyboards
from app.bot.callbacks import Nav, OrderCB, OrdersListCB
from app.bot.handlers.common import Context, build_context, show, toast
from app.bot.texts import Safe
from app.core.constants import OrderKind, OrderStatus
from app.core.logging import get_logger
from app.utils.formatting import format_datetime, order_icon
from app.utils.pagination import paginate

router = Router(name="orders")
logger = get_logger(__name__)

TITLES = {
    OrderKind.ACTIVATION: "SMS ACTIVATIONS",
    OrderKind.SMM: "SMM ORDERS",
}


@router.callback_query(Nav.filter(F.to == "orders"))
async def open_orders(query: CallbackQuery, state: FSMContext, **data):
    await state.clear()
    context = build_context(data)
    await show(
        query,
        context.text("orders.root"),
        keyboards.orders_root(context.texts, context.locale, context.smm.enabled),
    )


@router.callback_query(OrdersListCB.filter())
async def list_orders(query: CallbackQuery, callback_data: OrdersListCB, **data):
    context = build_context(data)
    kind = OrderKind(callback_data.kind)
    orders = await context.orders.list_for_user(query.from_user.id, kind)
    title = TITLES[kind]

    if not orders:
        await show(
            query,
            context.text("orders.empty", title=title),
            keyboards.orders_empty(context.texts, context.locale, kind.value),
        )
        return

    page = paginate(orders, callback_data.page, per_page=8)
    await show(
        query,
        context.text("orders.list", title=title, count=len(orders)),
        keyboards.orders_list(
            context.texts, context.locale, page, kind.value, context.settings.currency_symbol
        ),
    )


@router.callback_query(OrderCB.filter(F.action.in_({"detail", "refresh"})))
async def order_detail(query: CallbackQuery, callback_data: OrderCB, **data):
    """Show one order. Ownership is enforced by the repository, not the callback."""
    context = build_context(data)
    order = await context.orders.get_owned(callback_data.order_id, query.from_user.id)

    if callback_data.action == "refresh" and order.kind == OrderKind.SMM:
        order = await context.smm.refresh_status(order)

    await show(query, _render_order(context, order), keyboards.order_detail(
        context.texts, context.locale, order, order.kind
    ))


@router.callback_query(OrderCB.filter(F.action == "cancel"))
async def cancel_prompt(query: CallbackQuery, callback_data: OrderCB, **data):
    """Destructive action: confirm before doing it."""
    context = build_context(data)
    order = await context.orders.get_owned(callback_data.order_id, query.from_user.id)
    if OrderStatus(order.status).is_final:
        await toast(query, context.text("errors.duplicate_operation"), alert=True)
        return

    await show(
        query,
        context.text(
            "sms.cancel_confirm",
            order_id=order.id,
            phone=order.phone or "—",
            refund_policy=Safe(context.text("policies.refund")),
        ),
        keyboards.cancel_confirm(context.texts, context.locale, order.id),
    )


@router.callback_query(OrderCB.filter(F.action == "cancel_yes"))
async def cancel_order(query: CallbackQuery, callback_data: OrderCB, **data):
    context = build_context(data)
    order = await context.orders.cancel(callback_data.order_id, query.from_user.id)
    balance = await context.wallet.get_balance(query.from_user.id)
    await show(
        query,
        context.text(
            "sms.cancel_done",
            price=context.money(order.price),
            balance=context.money(balance),
        ),
        keyboards.back_home(context.texts, context.locale, back_to="orders"),
    )


def _render_order(context: Context, order) -> str:
    """Receipt view, shared by the order list and the post-purchase screen."""
    country_line = f"🌍 Country: {order.country_name}\n" if order.country_name else ""
    if order.sms_code:
        code_block = Safe(
            f"{context.texts.get('common.divider')}\n\n🔐 <b>Code:</b>\n<code>{order.sms_code}</code>"
        )
    elif OrderStatus(order.status).is_final:
        code_block = ""
    else:
        code_block = Safe(context.text("buy.waiting"))

    return context.text(
        "orders.detail",
        order_id=order.id,
        status_icon=order_icon(order.status),
        status=OrderStatus(order.status).value.title(),
        service=order.service_name,
        country_line=Safe(country_line),
        phone=order.phone or "—",
        price=context.money(order.price),
        created_at=format_datetime(order.created_at),
        code_block=code_block,
    )
