"""Handler routers, in dispatch order.

Admin is registered first so ``/admin`` cannot be shadowed, and the buy router
owns the shared confirm callback that the SMM flow delegates into.

Several modules have no router of their own: they register on another module's
router and are imported here purely so that registration happens.
"""

from aiogram import Router

from app.bot.handlers import (
    admin,
    buy,
    deposits,  # noqa: F401  -- registers on the wallet router
    favorites,  # noqa: F401  -- registers on the profile router
    help_center,  # noqa: F401  -- registers on the profile router
    manual_payments,
    manual_review,  # noqa: F401  -- registers on the manual_payments router
    navigation,
    orders,
    profile,
    referrals,  # noqa: F401  -- registers on the profile router
    smm,
    start,
    transfers,  # noqa: F401  -- registers on the wallet router
    wallet,
)


def build_router() -> Router:
    root = Router(name="root")
    root.include_routers(
        # /help, /balance, /orders, /cancel: checked before any flow router so
        # they interrupt an in-progress flow instead of being parsed as its
        # typed input.
        navigation.commands_router,
        admin.router,
        start.router,
        buy.router,
        orders.router,
        wallet.router,
        manual_payments.router,
        smm.router,
        profile.router,
        # Dead last: only reached once nothing else -- no command, no active
        # FSM state's handler -- has matched.
        navigation.fallback_router,
    )
    return root


__all__ = ["build_router"]
