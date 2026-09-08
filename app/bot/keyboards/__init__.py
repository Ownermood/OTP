"""Keyboard builders.

Every inline keyboard in the bot is built here, so navigation stays
consistent: long lists paginate through one shared control row, and every
screen below the main menu ends with Back and/or Home.
"""

from app.bot.keyboards.buy import activation, cancel_confirm, countries, purchase_confirm, services
from app.bot.keyboards.common import back_home, confirm_or_cancel, main_menu
from app.bot.keyboards.orders import (
    favorite_detail,
    favorites_list,
    order_detail,
    orders_list,
    orders_root,
)
from app.bot.keyboards.smm import smm_categories, smm_order, smm_services
from app.bot.keyboards.wallet import (
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
    "back_home",
    "cancel_confirm",
    "confirm_or_cancel",
    "countries",
    "favorite_detail",
    "favorites_list",
    "help_menu",
    "invoice",
    "main_menu",
    "order_detail",
    "orders_list",
    "orders_root",
    "payment_methods",
    "profile",
    "purchase_confirm",
    "referral",
    "services",
    "settings_menu",
    "smm_categories",
    "smm_order",
    "smm_services",
    "transactions_filters",
    "wallet",
]
