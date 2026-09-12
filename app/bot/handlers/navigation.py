"""Top-level commands and the catch-all fallback for text outside any flow.

``commands_router`` is registered before every flow router so /help, /balance,
/orders, /buy, /account, /support and /cancel work as an escape hatch from
*inside* a flow too -- a user stuck in the deposit-amount prompt can type
/cancel instead of a number and leave it, rather than that text being parsed
as the amount.

``fallback_router`` is registered dead last. Its handler is filtered on
``StateFilter(None)``, so it only ever sees a message once every other router
-- including every FSM-state-scoped handler -- has already had first refusal.
That is what keeps a stray line of text from ever being interpreted as a
deposit amount, a promo code, or any other typed input: the state-scoped
handler for that flow is always tried first, and the fallback simply cannot
match while a state is active.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot import keyboards
from app.bot.handlers.buy import _render_countries
from app.bot.handlers.common import build_context, show
from app.core.logging import get_logger

commands_router = Router(name="navigation_commands")
fallback_router = Router(name="navigation_fallback")
logger = get_logger(__name__)


@commands_router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext, **data) -> None:
    await state.clear()
    context = build_context(data)
    await show(
        message,
        context.text("help.main"),
        keyboards.help_menu(context.texts, context.locale, context.settings.support_url),
    )


@commands_router.message(Command("balance"))
async def cmd_balance(message: Message, state: FSMContext, **data) -> None:
    await state.clear()
    context = build_context(data)
    await show(
        message,
        context.text("wallet.main", balance=context.money(context.user.balance)),
        keyboards.wallet(context.texts, context.locale, context.settings.transfer_enabled),
    )


@commands_router.message(Command("orders"))
async def cmd_orders(message: Message, state: FSMContext, **data) -> None:
    await state.clear()
    context = build_context(data)
    await show(
        message,
        context.text("orders.root"),
        keyboards.orders_root(context.texts, context.locale, context.smm.enabled),
    )


@commands_router.message(Command("buy"))
async def cmd_buy(message: Message, state: FSMContext, **data) -> None:
    await state.clear()
    context = build_context(data)
    await _render_countries(message, context)


@commands_router.message(Command("account"))
async def cmd_account(message: Message, state: FSMContext, **data) -> None:
    await state.clear()
    context = build_context(data)
    stats = await context.users.stats(message.from_user.id)
    await show(
        message,
        context.text(
            "profile.main",
            name=context.user.full_name or context.user.username or "there",
            user_id=context.user.id,
            balance=context.money(context.user.balance),
            activations=stats.activations,
            smm_orders=stats.smm_orders,
            total_spent=context.money(stats.total_spent),
            referral_earned=context.money(stats.referral_earned),
        ),
        keyboards.profile(context.texts, context.locale),
    )


@commands_router.message(Command("support"))
async def cmd_support(message: Message, state: FSMContext, **data) -> None:
    """Same destination as /help: the help centre carries the support link."""
    await cmd_help(message, state, **data)


@commands_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, **data) -> None:
    """Escape hatch out of any FSM flow, from the keyboard rather than a button."""
    await state.clear()
    context = build_context(data)
    await show(
        message,
        context.text("common.cancelled"),
        keyboards.main_menu(context.texts, context.locale, context.smm.enabled),
    )


@fallback_router.message(StateFilter(None))
async def catch_all(message: Message, **data) -> None:
    """Text that matched no command and no flow. Never reached mid-flow."""
    context = build_context(data)
    await show(
        message,
        context.text("fallback"),
        keyboards.main_menu(context.texts, context.locale, context.smm.enabled),
    )
