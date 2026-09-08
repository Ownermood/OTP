"""Promo code listing and creation, flat or a percentage of a deposit."""

from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import AdminCB
from app.bot.handlers.admin.common import _back_button, _back_only, _guard, router
from app.bot.handlers.common import build_context, show
from app.bot.states import AdminStates
from app.core.exceptions import ValidationError
from app.core.money import format_money, parse_amount
from app.utils.validators import parse_positive_int, parse_promo_code


@router.callback_query(AdminCB.filter(F.action == "promo"))
async def promo_list(query: CallbackQuery, **data):
    context = build_context(data)
    _guard(context, "promo")

    promos = await context.promo.list_all()
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Create", callback_data=AdminCB(action="promo_new").pack())
    )
    builder.row(_back_button())

    lines = [
        f"🎟 <code>{p.code}</code> — "
        + (
            f"{p.percent}% of deposit"
            if p.percent
            else format_money(p.amount, context.settings.currency_symbol)
        )
        + f" · {p.used_count}/{p.max_activations} used"
        for p in promos[:15]
    ]
    body = "\n".join(lines) or context.text("common.empty")
    await show(
        query,
        context.text("admin.promo_list", count=len(promos)) + "\n\n" + body,
        builder.as_markup(),
    )


@router.callback_query(AdminCB.filter(F.action == "promo_new"))
async def promo_new(query: CallbackQuery, state: FSMContext, **data):
    context = build_context(data)
    _guard(context, "promo")
    await state.set_state(AdminStates.promo_code)
    await show(query, context.text("admin.promo_create_code"), _back_only())


@router.message(AdminStates.promo_code)
async def promo_code(message: Message, state: FSMContext, **data):
    context = build_context(data)
    _guard(context, "promo")
    code = parse_promo_code(message.text or "")
    await state.set_state(AdminStates.promo_amount)
    await state.update_data(promo_code=code)
    await show(message, context.text("admin.promo_create_amount", code=code), _back_only())


@router.message(AdminStates.promo_amount)
async def promo_amount(message: Message, state: FSMContext, **data):
    """Accept either a flat bonus (``50``) or a deposit percentage (``10%``)."""
    context = build_context(data)
    _guard(context, "promo")

    raw = (message.text or "").strip()
    if raw.endswith("%"):
        percent = parse_positive_int(raw.rstrip("%"), minimum=1, maximum=100)
        amount, label = 0, f"{percent}% of next deposit"
    else:
        percent = 0
        amount = parse_amount(raw)
        if amount is None:
            raise ValidationError("unparseable amount")
        label = format_money(amount, context.settings.currency_symbol)

    stored = await state.get_data()
    await state.set_state(AdminStates.promo_limit)
    await state.update_data(promo_amount=amount, promo_percent=percent)
    await show(
        message,
        context.text("admin.promo_create_limit", code=stored["promo_code"], amount=label),
        _back_only(),
    )


@router.message(AdminStates.promo_limit)
async def promo_limit(message: Message, state: FSMContext, **data):
    context = build_context(data)
    role = _guard(context, "promo")
    limit = parse_positive_int(message.text or "", minimum=1, maximum=1_000_000)

    stored = await state.get_data()
    await state.clear()
    percent = int(stored.get("promo_percent", 0))
    promo = await context.promo.create(
        code=stored["promo_code"],
        amount=int(stored["promo_amount"]),
        percent=percent,
        max_activations=limit,
        expires_at=None,
        min_deposit=0,
        created_by=message.from_user.id,
    )
    await context.admin.log(message.from_user.id, role, "promo_create", promo.code)
    await show(
        message,
        context.text(
            "admin.promo_created",
            code=promo.code,
            amount=(
                f"{promo.percent}% of next deposit"
                if promo.percent
                else format_money(promo.amount, context.settings.currency_symbol)
            ),
            limit=promo.max_activations,
        ),
        _back_only(),
    )


# -- broadcast --------------------------------------------------------------
