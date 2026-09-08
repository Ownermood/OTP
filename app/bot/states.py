"""FSM states.

FSM is used only where the user genuinely has to type something. Every state
group has a cancel path, and every handler that finishes or aborts a flow calls
``state.clear()`` -- a stuck state is a bug, not a feature.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class BuyStates(StatesGroup):
    searching_service = State()
    searching_country = State()


class RentalStates(StatesGroup):
    searching_country = State()
    entering_hours = State()


class PaymentStates(StatesGroup):
    entering_amount = State()


class ManualPaymentStates(StatesGroup):
    entering_amount = State()
    entering_utr = State()
    entering_proof = State()
    declining = State()


class PromoStates(StatesGroup):
    entering_code = State()


class TransferStates(StatesGroup):
    entering_username = State()
    entering_amount = State()


class SmmStates(StatesGroup):
    searching = State()
    entering_link = State()
    entering_quantity = State()


class AdminStates(StatesGroup):
    searching = State()
    entering_balance = State()
    entering_balance_reason = State()
    entering_ban_reason = State()
    broadcast_text = State()
    promo_code = State()
    promo_amount = State()
    promo_limit = State()
