"""Handler routers, in dispatch order.

Admin is registered first so ``/admin`` cannot be shadowed, and the buy router
owns the shared confirm callback that the rental and SMM flows delegate into.
"""

from aiogram import Router

from app.bot.handlers import admin, buy, orders, profile, rental, smm, start, wallet


def build_router() -> Router:
    root = Router(name="root")
    root.include_routers(
        admin.router,
        start.router,
        buy.router,
        rental.router,
        orders.router,
        wallet.router,
        smm.router,
        profile.router,
    )
    return root


__all__ = ["build_router"]
