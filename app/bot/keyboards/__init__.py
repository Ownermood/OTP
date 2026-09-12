"""Keyboard builders.

Every inline keyboard in the bot is built here, so navigation stays
consistent: long lists paginate through one shared control row, and every
screen below the main menu ends with Back and/or Home.
"""

from app.bot.keyboards.buy import (
    activation,
    cancel_confirm,
    country_grid,
    country_services,
    purchase_confirm,
)
from app.bot.keyboards.common import back_home, confirm_or_cancel, main_menu
from app.bot.keyboards.orders import (
    favorite_detail,
    favorites_list,
    order_detail,
    orders_empty,
    orders_list,
    orders_root,
)
from app.bot.keyboards.smm import smm_categories, smm_order, smm_services
from app.bot.keyboards.wallet import (
    amount_prompt,
    help_menu,
    invoice,
    payment_methods,
    profile,
    referral,
    settings_menu,
    transactions_filters,
    wallet,
)

__all__ = [
    "activation",
    "amount_prompt",
    "back_home",
    "cancel_confirm",
    "confirm_or_cancel",
    "country_grid",
    "country_services",
    "favorite_detail",
    "favorites_list",
    "help_menu",
    "invoice",
    "main_menu",
    "order_detail",
    "orders_empty",
    "orders_list",
    "orders_root",
    "payment_methods",
    "profile",
    "purchase_confirm",
    "referral",
    "settings_menu",
    "smm_categories",
    "smm_order",
    "smm_services",
    "transactions_filters",
    "wallet",
]
